"""test_core.py — 核心链路回归测试（基于 D0 真实样本数据）。

运行: python3 tests/test_core.py
覆盖: 营养解析 / 目标计算 / 菜单对齐 / 三餐组合多场景
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from nutrition import parse_nutrition_text, daily_target  # noqa: E402
from meal_planner import (  # noqa: E402
    parse_menu_text, align_menu_with_nutrition, build_day_plan,
)

SAMPLES = Path(__file__).resolve().parent.parent / "docs" / "samples"


def load_foods():
    text = json.load(open(SAMPLES / "nutrition-raw.txt"))
    return parse_nutrition_text(text)


def load_plannable(foods):
    menu = parse_menu_text(open(SAMPLES / "query-meals-raw.txt").read())
    return align_menu_with_nutrition(menu, foods)


def test_parse_nutrition():
    foods = load_foods()
    assert 150 <= len(foods) <= 165, f"餐品数异常: {len(foods)}"
    bigmac = next(f for f in foods if f.name == "巨无霸")
    assert (bigmac.kcal, bigmac.protein) == (513.0, 27.0)
    names = {f.name for f in foods}
    assert len(names) == len(foods), "存在重复名称"
    print(f"[PASS] parse_nutrition: {len(foods)} 餐品")


def test_daily_target():
    t = daily_target("male", 70, 175, 28, "sedentary", "cut")
    assert 1400 < t.kcal < 2000
    assert t.protein_g == 126.0          # 1.8 * 70
    t2 = daily_target("female", 55, 162, 30, "light", "balance")
    assert t2.kcal > t.kcal * 0.8
    for bad in ("unknown-goal",):
        try:
            daily_target("male", 70, 175, 28, "sedentary", bad)
            raise AssertionError("非法 goal 未被拒绝")
        except ValueError:
            pass
    print("[PASS] daily_target")


def test_menu_align():
    foods = load_foods()
    plannable = load_plannable(foods)
    assert len(plannable) >= 30, f"对齐数量过少: {len(plannable)}"
    cats = {p.category for p in plannable}
    assert {"主食", "饮品"} <= cats
    # 汉堡类不得被误判为小食
    burger = next(p for p in plannable if p.menu.name == "麦辣鸡腿汉堡")
    assert burger.category == "主食"
    print(f"[PASS] menu_align: {len(plannable)} 项对齐")


def test_build_day_plan():
    foods = load_foods()
    plannable = load_plannable(foods)
    cases = [
        (dict(sex="male", weight_kg=70, height_cm=175, age=28,
              activity="sedentary", goal="cut"), 120, 10),
        (dict(sex="female", weight_kg=55, height_cm=162, age=30,
              activity="light", goal="balance"), 100, 10),
        (dict(sex="male", weight_kg=85, height_cm=180, age=35,
              activity="sedentary", goal="cut"), None, 6),
        (dict(sex="male", weight_kg=65, height_cm=170, age=24,
              activity="moderate", goal="bulk"), 150, 10),
    ]
    for i, (kw, budget, kcal_tol) in enumerate(cases, 1):
        t = daily_target(**kw)
        plan = build_day_plan(plannable, t, budget=budget, seed=7)
        tot = plan["totals"]
        err = abs(tot["kcal"] - t.kcal) / t.kcal * 100
        assert err <= kcal_tol, f"case{i} 热量误差 {err:.1f}%"
        assert all(meal["items"] for meal in plan["meals"].values()), \
            f"case{i} 存在空餐"
        # 全天餐品去重
        codes = [it["code"] for meal in plan["meals"].values() for it in meal["items"]]
        assert len(codes) == len(set(codes)), f"case{i} 跨餐重复选品"
        if budget is not None and not plan["over_budget"]:
            assert tot["price"] <= budget + 0.01
        print(f"[PASS] build_day_plan case{i}: 误差 {err:.1f}%, ¥{tot['price']}")


def test_report():
    """报告生成：含关键区块、服务端来源字符串被转义、无裸模板占位符。"""
    import re as _re
    from report import generate_report
    result = {
        "store": {"storeCode": "1450724", "storeName": "测试门店<x&y>",
                  "address": "某路1号"},
        "profile": {"sex": "male", "weight_kg": 70, "height_cm": 175,
                    "age": 28, "activity": "sedentary", "goal": "cut",
                    "budget": 120},
        "target": {"kcal": 1592, "protein_g": 126, "fat_g": 44,
                   "carbs_g": 173, "sodium_max_mg": 2000},
        "meals": {"breakfast": {"name": "早餐",
                                "items": [{"code": "1", "name": "麦香鱼<i>",
                                           "price": 22.5, "kcal": 325,
                                           "protein": 16, "fat": 13,
                                           "carbs": 32, "sodium": 720}]}},
        "totals": {"kcal": 325, "protein": 16, "fat": 13, "carbs": 32,
                   "sodium": 720, "price": 22.5},
        "official_price": 22.5, "discount": 0.0,
        "over_budget": False, "score": 12.3,
    }
    out = generate_report(result)
    for key in ("营养达成雷达", "三餐热量分布", "三餐明细", "营养师点评", "官方算价"):
        assert key in out, f"缺少区块: {key}"
    assert "麦香鱼&lt;i&gt;" in out, "餐品名未转义"
    assert "测试门店&lt;x&amp;y&gt;" in out, "门店名未转义"
    assert not _re.search(r"\{[a-z_]+\}", _re.sub(r"\$\{", "$<", out)), \
        "存在未替换的模板占位符"
    print("[PASS] report generate & escape")


if __name__ == "__main__":
    test_parse_nutrition()
    test_daily_target()
    test_menu_align()
    test_build_day_plan()
    test_report()
    print("\n全部通过 ✅")
