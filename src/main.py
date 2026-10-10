"""main.py — 麦麦轻食官 CLI 入口。

用法示例:
    export MCD_MCP_TOKEN=你的Token
    python main.py --sex male --weight 70 --height 175 --age 28 \
        --goal cut --budget 120 --city 上海市 --keyword 麦当劳

流程: 营养知识库(带本地缓存) → 门店 → 菜单 → 三餐规划 → 官方算价 → 输出 JSON
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcd_client import McpClient, McpError                     # noqa: E402
from nutrition import parse_nutrition_text, daily_target       # noqa: E402
from meal_planner import (                                     # noqa: E402
    parse_menu_text, align_menu_with_nutrition, build_day_plan,
)
from coupon import (                                           # noqa: E402
    price_without_coupon, best_price_with_coupons,
    list_my_coupons, bind_all_coupons,
)

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"


# --------------------------------------------------------------------- #
def get_foods(client, use_cache: bool = True):
    """营养知识库：优先本地缓存（数据按月更新，缓存一天足够）。"""
    cache = CACHE_DIR / "nutrition.json"
    if use_cache and cache.exists():
        import time
        if time.time() - cache.stat().st_mtime < 86400:
            foods_raw = json.load(open(cache))
            return parse_nutrition_text(foods_raw)
    text = client.call("list-nutrition-foods")
    CACHE_DIR.mkdir(exist_ok=True)
    json.dump(text, open(cache, "w"))
    return parse_nutrition_text(text)


def pick_store(client, city: str, keyword: str, store_code: str | None) -> dict:
    """指定 storeCode 直接用；否则按城市+关键词搜最近一家营业中门店。"""
    if store_code:
        return {"storeCode": store_code, "storeName": f"指定门店 {store_code}"}
    text = client.call("query-nearby-stores",
                       {"beType": 1, "searchType": 2, "city": city, "keyword": keyword})
    m = __import__("re").search(r'\{"success":true.*', text, __import__("re").S)
    if not m:
        raise McpError(f"门店查询失败: {text[:200]}")
    snippet = m.group(0)
    end = snippet.rfind("}")
    while end > 0:
        try:
            stores = json.loads(snippet[:end + 1])["data"]
            break
        except json.JSONDecodeError:
            end = snippet.rfind("}", 0, end)
    if not stores:
        raise McpError("未找到可用门店，请更换城市/关键词")
    s = stores[0]
    return {"storeCode": s["storeCode"], "storeName": s["storeName"],
            "address": s.get("address", ""), "distance": s.get("distance")}


# --------------------------------------------------------------------- #
def run(args) -> dict:
    client = McpClient(token=args.token)

    print("① 拉取营养知识库…")
    foods = get_foods(client, use_cache=not args.no_cache)
    print(f"   {len(foods)} 个餐品营养数据")

    print("② 查询门店…")
    store = pick_store(client, args.city, args.keyword, args.store_code)
    print(f"   {store['storeName']} ({store.get('address', '')})")

    print("③ 拉取菜单并对齐营养…")
    meals_text = client.call("query-meals",
                             {"storeCode": store["storeCode"],
                              "orderType": 1, "beType": 1})
    menu = parse_menu_text(meals_text)
    plannable = align_menu_with_nutrition(menu, foods)
    print(f"   菜单 {len(menu)} 项，可规划 {len(plannable)} 项")

    print("④ 生成三餐方案…")
    target = daily_target(args.sex, args.weight, args.height, args.age,
                          args.activity, args.goal)
    plan = build_day_plan(plannable, target, budget=args.budget, seed=args.seed)
    tot = plan["totals"]
    print(f"   热量 {tot['kcal']}/{target.kcal:.0f} kcal | 蛋白 {tot['protein']}g"
          f" | 金额 ¥{tot['price']}")

    print("⑤ 官方算价（含用券试算）…")
    items = [{"productCode": it["code"], "quantity": 1}
             for meal in plan["meals"].values() for it in meal["items"]]
    try:
        pricing, src = None, ""
        if args.bind and not args.no_coupon:
            # 领券（副作用）并捕获券 ID——couponId/couponCode 仅在领券结果中出现
            coupons = bind_all_coupons(client)
            print(f"   领取/持有券 {len(coupons)} 张")
            if coupons:
                pricing = best_price_with_coupons(
                    client, store["storeCode"], 1, 1, items, coupons)
                src = f"用券试算（{len(coupons)} 张）"
        if pricing is None:
            pricing = price_without_coupon(
                client, store["storeCode"], 1, 1, items)
            src = "无券原价"
        print(f"   {src}: 应付 ¥{pricing['price']}"
              + (f"（优惠 ¥{pricing['discount']}）" if pricing["discount"] else ""))
    except McpError as e:
        pricing, src = None, f"算价失败: {e}"
        print(f"   ⚠️ {src}")

    result = {
        "store": store,
        "profile": {"sex": args.sex, "weight_kg": args.weight,
                    "height_cm": args.height, "age": args.age,
                    "activity": args.activity, "goal": args.goal,
                    "budget": args.budget},
        "target": plan["target"],
        "meals": plan["meals"],
        "totals": tot,
        "menu_price": tot["price"],
        "official_price": pricing["price"] if pricing else None,
        "discount": pricing["discount"] if pricing else None,
        "over_budget": plan["over_budget"],
        "score": plan["score"],
    }
    if args.report:
        from report import generate_report
        out = args.report if isinstance(args.report, str) else "report.html"
        Path(out).write_text(generate_report(result), encoding="utf-8")
        print(f"\n📊 营养报告已生成: {out}")
    return result


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="麦麦轻食官 — 麦当劳健康点餐助手")
    p.add_argument("--sex", choices=["male", "female"], default="male")
    p.add_argument("--weight", type=float, required=True, help="体重 kg")
    p.add_argument("--height", type=float, required=True, help="身高 cm")
    p.add_argument("--age", type=int, required=True)
    p.add_argument("--activity", default="sedentary",
                   choices=["sedentary", "light", "moderate", "active"])
    p.add_argument("--goal", default="cut", choices=["cut", "bulk", "balance"])
    p.add_argument("--budget", type=float, default=None, help="每日预算（元）")
    p.add_argument("--city", default="上海市")
    p.add_argument("--keyword", default="麦当劳")
    p.add_argument("--store-code", default=None, help="直接指定门店编码")
    p.add_argument("--token", default=os.environ.get("MCD_MCP_TOKEN"),
                   help="MCP Token，默认读环境变量 MCD_MCP_TOKEN")
    p.add_argument("--no-cache", action="store_true", help="强制刷新营养缓存")
    p.add_argument("--no-coupon", action="store_true", help="跳过用券试算")
    p.add_argument("--bind", action="store_true",
                   help="一键领取麦麦省可用券（⚠️ 真实入账），随后用券试算")
    p.add_argument("--seed", type=int, default=None, help="固定随机种子（复现用）")
    p.add_argument("-o", "--output", default=None, help="结果 JSON 输出路径")
    p.add_argument("--report", nargs="?", const="report.html", default=None,
                   help="同时生成可视化营养报告 HTML（可指定路径）")
    args = p.parse_args(argv)
    if not args.token:
        p.error("缺少 Token：请设置环境变量 MCD_MCP_TOKEN 或传 --token")
    return args


if __name__ == "__main__":
    cli_args = parse_args()
    res = run(cli_args)
    print("\n===== 麦麦轻食官 · 一日三餐方案 =====")
    for slot, meal in res["meals"].items():
        names = " + ".join(f"{i['name']}(¥{i['price']})" for i in meal["items"])
        print(f"{meal['name']}: {names or '(轻食)'}")
    print(f"合计营养: {res['totals']}")
    print(f"菜单价 ¥{res['menu_price']}"
          + (f" / 官方算价 ¥{res['official_price']}" if res["official_price"] else ""))
    if res["over_budget"]:
        print("⚠️ 该预算下无法完全满足营养目标，建议上调预算或接受偏差")
    if cli_args.output:
        Path(cli_args.output).write_text(json.dumps(res, ensure_ascii=False, indent=2))
        print(f"\n结果已写入 {cli_args.output}")
