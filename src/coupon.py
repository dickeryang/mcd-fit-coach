"""coupon.py — 门店可用券查询与"券-商品直配"最优算价。

链路（真实契约，已实测）:
1. query-store-coupons(storeCode, orderType, beType)
      → 一次返回指定门店/订单类型下【可用券 + 有效券码 + 适用商品编码】
2. 本地把券按 products[].productCode 直配到方案商品位（无需盲试）
3. calculate-price 携带 couponId + couponCode 单次算价（失败自动回退原价）

辅助（可选 / 展示用）:
- available-coupons     → 查可领券列表（只读）
- auto-bind-coupons     → 一键领券（⚠️ 有副作用：真实入账，需用户确认）
- query-my-coupons      → 查卡包已有券（仅标题/价格/有效期，不含券码）

关键经验（曾踩的坑）:
- 券码必须取自 `query-store-coupons`，**不能**用 `auto-bind-coupons` 领取结果里的
  券码——后者带 couponId 但 couponCode 无效，算价会报 600012「未找到优惠券」。
- `query-my-coupons` 官方明确不做门店/渠道校验，不承诺可用于当前订单，只能展示。
- 同一 couponId 可对应多个 couponCode，解析必须按 couponId 分组。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class StoreCoupon:
    """门店维度的一张可用券（query-store-coupons 返回）。"""
    coupon_id: str
    coupon_code: str
    title: str = ""
    valid_range: str = ""
    products: list[dict] = field(default_factory=list)  # [{code, name}]
    promotion_id: str = ""

    @property
    def product_codes(self) -> set[str]:
        return {p.get("code") for p in self.products if p.get("code")}


# --------------------------------------------------------------------- #
# 门店可用券（核心）
# --------------------------------------------------------------------- #

def query_store_coupons(client, store_code: str, order_type: int,
                        be_type: int, reservation_date: str | None = None,
                        ) -> list[StoreCoupon]:
    """查询指定门店/订单类型下的可用券（含有效券码与适用商品）。

    这是本项目获取「可用券码」的唯一正确来源。
    """
    args: dict = {"storeCode": store_code, "orderType": order_type,
                  "beType": be_type}
    if reservation_date:
        args["reservationDate"] = reservation_date
    obj = client.call_json("query-store-coupons", args)
    data = obj.get("data") or []
    return [_to_store_coupon(c) for c in data]


def _to_store_coupon(raw: dict) -> StoreCoupon:
    return StoreCoupon(
        coupon_id=str(raw.get("couponId", "")),
        coupon_code=str(raw.get("couponCode", "")),
        title=raw.get("title", "") or "",
        valid_range=raw.get("tradeDateTime", "") or "",
        products=[{"code": str(p.get("productCode", "")),
                   "name": p.get("productName", "") or ""}
                  for p in (raw.get("products") or [])],
        promotion_id=str(raw.get("promotionId", "")),
    )


def match_coupons_to_items(items: list[dict],
                           coupons: list[StoreCoupon]) -> tuple[list[dict], list[StoreCoupon]]:
    """把可用券按适用商品直配到方案商品位。

    规则：每个商品位至多挂一张券；券的 products 含该商品编码则命中。
    券无适用商品信息时视为整单券，挂到首个未占用商品位。

    返回 (带券 items 副本, 实际挂载的券列表)。不修改入参。
    """
    codes = [it["productCode"] for it in items]
    used: set[int] = set()
    attach: dict[int, StoreCoupon] = {}

    for cp in coupons:
        if not cp.coupon_id and not cp.coupon_code:
            continue
        target = None
        cp_codes = cp.product_codes
        if cp_codes:
            for i, code in enumerate(codes):
                if i not in used and code in cp_codes:
                    target = i
                    break
        else:
            for i in range(len(codes)):
                if i not in used:
                    target = i
                    break
        if target is not None:
            used.add(target)
            attach[target] = cp

    priced: list[dict] = []
    for i, it in enumerate(items):
        item = dict(it)
        cp = attach.get(i)
        if cp is not None:
            item["couponId"] = cp.coupon_id
            if cp.coupon_code:
                item["couponCode"] = cp.coupon_code
        priced.append(item)

    applied = [attach[i] for i in sorted(attach)]
    return priced, applied


def price_with_store_coupons(client, store_code: str, order_type: int,
                             be_type: int, items: list[dict],
                             reservation_date: str | None = None) -> dict:
    """一条链路完成：查门店可用券 → 券-商品直配 → 单次算价。

    - 无可用券或挂载后算价失败：自动回退无券原价（主流程零影响）
    - 结果不低于原价：同样回退原价
    返回摘要 dict（元），并附 `coupons` 字段（可用券 + 命中券）。
    """
    base = price_without_coupon(client, store_code, order_type, be_type,
                                items, reservation_date=reservation_date)
    try:
        coupons = query_store_coupons(client, store_code, order_type, be_type,
                                      reservation_date)
    except Exception:
        coupons = []

    priced_items, applied = match_coupons_to_items(items, coupons)
    result = dict(base)
    result["available_coupons"] = coupons
    result["applied_coupons"] = []

    if not applied:
        return result

    try:
        data = client.call_json("calculate-price", {
            "storeCode": store_code, "orderType": order_type,
            "beType": be_type, "items": priced_items,
        })["data"]
    except Exception:
        return result  # 券组合被拒：回退原价

    summary = _price_summary(data)
    if summary["price"] <= base["price"] + 0.005:
        # discount 统一为「相对无券价的真实节省额」，避免服务端标价口径造成误导
        summary["discount"] = round(base["price"] - summary["price"], 2)
        summary["available_coupons"] = coupons
        summary["applied_coupons"] = applied
        return summary
    return result


# --------------------------------------------------------------------- #
# 无券算价
# --------------------------------------------------------------------- #

def price_without_coupon(client, store_code: str, order_type: int,
                         be_type: int, items: list[dict],
                         reservation_date: str | None = None) -> dict:
    """无券算价，返回标准化价格摘要（单位：元）。"""
    args: dict = {"storeCode": store_code, "orderType": order_type,
                  "beType": be_type, "items": items}
    if reservation_date:
        args["reservationDate"] = reservation_date
    data = client.call_json("calculate-price", args)["data"]
    summary = _price_summary(data)
    summary["available_coupons"] = []
    summary["applied_coupons"] = []
    return summary


def _price_summary(data: dict) -> dict:
    """calculate-price data → 统一摘要（分 → 元）。"""
    return {
        "price": data.get("price", 0) / 100.0,
        "original": data.get("originalPrice", 0) / 100.0,
        "discount": data.get("discount", 0) / 100.0,
        "take_way_list": [
            {"code": tw.get("code"), "title": tw.get("title")}
            for tw in data.get("takeWayList", [])
        ],
        "products": [
            {"code": p.get("productCode"), "name": p.get("productName"),
             "quantity": p.get("quantity"),
             "subtotal": p.get("subtotal", 0) / 100.0}
            for p in data.get("productList", [])
        ],
    }


# --------------------------------------------------------------------- #
# 领券 / 卡包（展示与可选副作用）
# --------------------------------------------------------------------- #

def list_available_coupons(client) -> list[dict]:
    """查询麦麦省当前可领取的券（只读，尽力而为）。"""
    text = client.call("available-coupons")
    titles = re.findall(r"优惠券标题[:：]\s*(.+)", text)
    return [{"title": t.strip()} for t in titles]


def bind_all_coupons(client) -> list[dict]:
    """一键领取麦麦省全部可用券。⚠️ 有副作用：真实写入用户卡包。

    仅用于「顺便领券」，不再作为获取券码的手段（券码请用
    query_store_coupons）。返回领取到的券（尽力解析，可能为空）。
    """
    text = client.call("auto-bind-coupons")
    return [{"title": t.strip()}
            for t in re.findall(r"-\s*(.+?)\s*\n\s*-\s*couponId", text)]


def list_my_coupons(client) -> list[str]:
    """查询卡包已有券标题（只读；该接口不含券码，不能用于算价）。"""
    text = client.call("query-my-coupons", {"page": "1", "pageSize": "200"})
    if "暂无" in text:
        return []
    return [t.strip() for t in re.findall(r"^##\s+(.+)$", text, re.M)]
