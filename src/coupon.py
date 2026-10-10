"""coupon.py — 优惠券领取、卡包查询与"最优用券算价"。

链路：
1. available-coupons        → 查可领券列表（只读）
2. auto-bind-coupons        → 一键领券（⚠️ 有副作用：真实入账，需用户确认）
3. query-my-coupons         → 查卡包已有券（只读）
4. calculate-price          → 携带 couponId/couponCode 逐组合试算，取最低价

说明：MVP 采用"贪心试算"策略——对每张卡包券 × 方案内每个商品逐一
携带算价（服务端校验券的适用性，不适用会返回原价或报错），取总价最低
的组合。若后续发现券与商品的映射字段，可替换为直配策略减少调用量。
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Coupon:
    """卡包中的一张券（字段以服务端实际返回为准，做防御性解析）。"""
    coupon_id: str
    coupon_code: str
    title: str = ""


# --------------------------------------------------------------------- #
# 领券与卡包
# --------------------------------------------------------------------- #

def list_available_coupons(client) -> list[dict]:
    """查询麦麦省当前可领取的券（只读）。返回原始解析结果列表（尽力而为）。"""
    text = client.call("available-coupons")
    titles = re.findall(r"优惠券标题[:：]\s*(.+)", text)
    return [{"title": t.strip()} for t in titles]


def bind_all_coupons(client) -> list[Coupon]:
    """一键领取麦麦省全部可用券。⚠️ 有副作用：真实写入用户卡包。

    返回领取成功的券列表（含 couponId/couponCode——这两个字段只在
    领券结果中出现，卡包查询接口不含，必须在此捕获）。
    """
    text = client.call("auto-bind-coupons")
    return _parse_bind_result(text)


def _parse_bind_result(text: str) -> list[Coupon]:
    """解析领券结果文本 → Coupon 列表。

    格式:
        - 券标题
          - couponId：XXXX
          - couponCode：MCDXXXX
    """
    coupons: list[Coupon] = []
    pattern = re.compile(
        r"-\s*(.+?)\s*\n\s*-\s*couponId[：:]\s*(\w+)\s*\n\s*-\s*couponCode[：:]\s*(\w+)")
    for title, cid, ccode in pattern.findall(text):
        coupons.append(Coupon(coupon_id=cid, coupon_code=ccode,
                              title=title.strip()))
    return coupons


def list_my_coupons(client) -> list[str]:
    """查询卡包已有券（只读）。返回券标题列表（该接口不含券 ID）。"""
    text = client.call("query-my-coupons", {"page": "1", "pageSize": "200"})
    if "暂无" in text:
        return []
    return [t.strip() for t in re.findall(r"^##\s+(.+)$", text, re.M)]


# --------------------------------------------------------------------- #
# 最优用券算价
# --------------------------------------------------------------------- #

def price_without_coupon(client, store_code: str, order_type: int,
                         be_type: int, items: list[dict]) -> dict:
    """无券算价，返回标准化的价格摘要（单位：元）。"""
    data = client.call_json("calculate-price", {
        "storeCode": store_code, "orderType": order_type, "beType": be_type,
        "items": items,
    })["data"]
    return _price_summary(data)


def best_price_with_coupons(client, store_code: str, order_type: int,
                            be_type: int, items: list[dict],
                            coupons: list[Coupon],
                            max_calls: int = 60) -> dict:
    """贪心试算：每张券 × 每个商品位逐一携带算价，返回最低价方案。

    返回:
        {"price": 元, "discount": 元, "applied": {商品code: Coupon},
         "raw": 最低价原始返回}
    若无券或全部试算失败，返回与 price_without_coupon 等价的结果。
    """
    base = price_without_coupon(client, store_code, order_type, be_type, items)
    best = {"price": base["price"], "discount": base["discount"],
            "applied": {}, "raw": None}
    if not coupons:
        return best

    calls = 0
    product_codes = [it["productCode"] for it in items]
    for coupon in coupons:
        if calls >= max_calls:
            break
        for pcode in product_codes:
            if calls >= max_calls:
                break
            trial_items = []
            for it in items:
                trial = dict(it)
                if trial["productCode"] == pcode:
                    trial["couponId"] = coupon.coupon_id
                    if coupon.coupon_code:
                        trial["couponCode"] = coupon.coupon_code
                trial_items.append(trial)
            calls += 1
            try:
                data = client.call_json("calculate-price", {
                    "storeCode": store_code, "orderType": order_type,
                    "beType": be_type, "items": trial_items,
                })["data"]
            except Exception:
                continue  # 券不适用/参数被拒：跳过该组合
            summary = _price_summary(data)
            if summary["price"] < best["price"] - 0.005:
                best = {"price": summary["price"],
                        "discount": summary["discount"],
                        "applied": {pcode: coupon}, "raw": data}
    return best


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
             "quantity": p.get("quantity"), "subtotal": p.get("subtotal", 0) / 100.0}
            for p in data.get("productList", [])
        ],
    }
