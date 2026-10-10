"""meal_planner.py — 菜单解析、营养对齐与一日三餐组合。

链路：query-meals 原始返回 → MenuItem 列表 → 与营养知识库按名称对齐
     → 按每日目标（早 30% / 午 40% / 晚 30%）随机重启贪心搜索最优组合。

组合策略（MVP）：
- 每餐结构 = 主食(汉堡/卷) 或 早餐主项 + 小食(可选) + 饮品
- 评分 = 热量误差 + 蛋白误差 + 脂肪误差 + 钠超限惩罚 + 价格预算惩罚
- 随机重启 N 轮取最优，保证稳定性
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, field

from nutrition import DailyTarget, Food

# --------------------------------------------------------------------- #
# 菜单解析
# --------------------------------------------------------------------- #

@dataclass
class MenuItem:
    """菜单中的一个可选餐品（来自 query-meals）。"""
    code: str
    name: str
    price: float
    categories: list[str] = field(default_factory=list)
    can_with_order: bool = True


def parse_menu_text(text: str) -> list[MenuItem]:
    """解析 `query-meals` 返回 text → MenuItem 列表（含价格与所属分类）。"""
    m = re.search(r'\{"success":.*', text, re.S)
    if not m:
        raise ValueError("query-meals 返回中未找到 JSON")
    snippet = m.group(0)
    end = snippet.rfind("}")
    data = None
    while end > 0:
        try:
            data = json.loads(snippet[:end + 1])
            break
        except json.JSONDecodeError:
            end = snippet.rfind("}", 0, end)
    if not data or not data.get("success"):
        raise ValueError(f"query-meals 业务失败: {data}")

    items: dict[str, MenuItem] = {}
    for cat in data["data"]["categories"]:
        cat_name = cat.get("name", "").replace("\n", "")
        for meal in cat.get("meals", []):
            code = str(meal.get("code", ""))
            detail = data["data"]["meals"].get(code, {})
            name = detail.get("name") or meal.get("name") or ""
            if not code or not name:
                continue
            try:
                price = float(detail.get("currentPrice") or 0)
            except (TypeError, ValueError):
                price = 0.0
            if code in items:
                items[code].categories.append(cat_name)
            else:
                items[code] = MenuItem(code=code, name=name, price=price,
                                       categories=[cat_name],
                                       can_with_order=bool(detail.get("canWithOrder", True)))
    return list(items.values())


# --------------------------------------------------------------------- #
# 菜单 × 营养对齐
# --------------------------------------------------------------------- #

# 组合餐与周边商品：无独立营养或不可拆解，不参与规划
_EXCLUDE_RE = re.compile(
    r"(套餐|四件套|三件套|双人|多人|拼盘|1\+1|口福|乐园|组合|随心配|随心选"
    r"|单品精选|周边|帽|捶|挠|玩偶|玩具|酱$)")


def _normalize(name: str) -> str:
    """名称归一化：全角括号/引号转半角、去空白与装饰符号、转小写。"""
    name = name.replace("（", "(").replace("）", ")")
    name = name.replace("“", '"').replace("”", '"').replace("''", "'")
    return re.sub(r"[\s【】\"\"'·™®%]+", "", name).lower()


# 菜单简化名 → 营养表全名的规格偏好：优先中杯，其次最短名
_SIZE_PREFERENCE = ("中杯", "小杯", "标准", "5块", "2块")


def align_menu_with_nutrition(menu: list[MenuItem], foods: list[Food]) -> list["PlannableItem"]:
    """将菜单与营养表按名称对齐，产出可参与规划的餐品。

    匹配规则（按优先级）：
    1. 归一化名称完全相等；
    2. 互为前缀（如菜单"板烧鸡腿堡" vs 营养表"板烧鸡腿堡"）；
    3. 包含关系（如菜单"可乐" vs 营养表"可乐中杯"）——候选中按
       规格偏好（中杯 > 小杯 > …）与名称长度取最优。
    套餐/四件套/周边商品不参与 MVP 规划。
    """
    plannable: list[PlannableItem] = []
    used: set[str] = set()  # 同一营养项只挂到第一个菜单项，避免重复
    for item in menu:
        if _EXCLUDE_RE.search(item.name):
            continue
        key = _normalize(item.name)
        if not key:
            continue
        food = None
        # 1) 完全相等
        for f in foods:
            nk = _normalize(f.name)
            if nk == key and nk not in used:
                food = f
                break
        # 2) 互为前缀
        if food is None:
            for f in foods:
                nk = _normalize(f.name)
                if nk not in used and (nk.startswith(key) or key.startswith(nk)):
                    food = f
                    break
        # 3) 包含关系 + 规格偏好
        if food is None:
            candidates = [f for f in foods
                          if _normalize(f.name) not in used
                          and (key in _normalize(f.name) or _normalize(f.name) in key)]
            if candidates:
                def rank(f: Food) -> tuple:
                    nk = _normalize(f.name)
                    pref = next((i for i, s in enumerate(_SIZE_PREFERENCE)
                                 if s in nk), len(_SIZE_PREFERENCE))
                    return (pref, len(nk))
                food = sorted(candidates, key=rank)[0]
        if food is not None and _normalize(food.name) not in used:
            used.add(_normalize(food.name))
            plannable.append(PlannableItem(menu=item, food=food))
    return plannable


@dataclass
class PlannableItem:
    """完成营养对齐的可规划餐品。"""
    menu: MenuItem
    food: Food

    @property
    def kcal(self) -> float:
        return self.food.kcal

    @property
    def category(self) -> str:
        return self.food.category


# --------------------------------------------------------------------- #
# 一日三餐组合
# --------------------------------------------------------------------- #

_MEAL_SPLITS = {"breakfast": 0.30, "lunch": 0.40, "dinner": 0.30}
_MEAL_NAMES = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐"}

# 各餐位允许的品类（按优先级）：主食项 + 小食 + 饮品
_SLOT_MAIN_CATS = {
    "breakfast": ("早餐", "主食"),
    "lunch": ("主食",),
    "dinner": ("主食",),
}
_SLOT_SIDE_CATS = ("小食",)
_SLOT_DRINK_CATS = ("饮品",)


def build_day_plan(plannable: list[PlannableItem], target: DailyTarget,
                   budget: float | None = None,
                   restarts: int = 400, topk: int = 40,
                   seed: int | None = None) -> dict:
    """两阶段规划：餐位全枚举 Top-K + 日期间随机重组。

    阶段一：每个餐位枚举全部 (主餐, 小食, 饮品) 组合（含缺省，即"轻食"），
           按餐位营养偏差取 Top-K。
    阶段二：多轮随机重组——每轮为各餐位选一个组合（带全天去重惩罚与
           预算压力），计算全天评分，保留最优。

    返回:
        {"meals": {...}, "score": float, "target": {...}, "totals": {...}}
    """
    rng = random.Random(seed)
    mains_by_slot = {s: [p for p in plannable if p.category in cats]
                     for s, cats in _SLOT_MAIN_CATS.items()}
    sides = [p for p in plannable if p.category in _SLOT_SIDE_CATS]
    drinks = [p for p in plannable if p.category in _SLOT_DRINK_CATS]
    for slot, pool in mains_by_slot.items():
        if not pool:
            raise ValueError(f"餐位 {slot} 无可规划主餐")
    if not drinks:
        raise ValueError("无可规划饮品")

    # ---- 阶段一：枚举各餐位组合 ----
    slot_combos: dict[str, list[tuple[float, tuple]]] = {}
    for slot in ("breakfast", "lunch", "dinner"):
        share = _MEAL_SPLITS[slot]
        slot_combos[slot] = _enumerate_slot_combos(
            mains_by_slot[slot], sides, drinks,
            kcal=target.kcal * share,
            protein=target.protein_g * share,
            fat=target.fat_g * share,
            sodium_cap=target.sodium_max_mg * share,
            topk=topk)

    # ---- 阶段二：日期间多轮重组 ----
    best_plan, best_score = None, float("inf")
    for _ in range(max(restarts, 1)):
        plan, score = _assemble_day(rng, slot_combos, target, budget)
        if score < best_score:
            best_plan, best_score = plan, score

    totals = _totals(best_plan)
    return {"meals": best_plan, "score": round(best_score, 3),
            "target": target.as_dict(), "totals": totals,
            "over_budget": (budget is not None and totals["price"] > budget + 0.01)}


def _enumerate_slot_combos(mains, sides, drinks, kcal, protein, fat,
                           sodium_cap, topk):
    """枚举一个餐位的全部 (主餐, 小食, 饮品) 组合，返回按偏差排序的 Top-K。

    任一分量可为 None（轻食组合）；主餐与小食不能同时为 None。
    """
    combos = []
    for m in list(mains) + [None]:
        for s in list(sides) + [None]:
            if m is None and s is None:
                continue  # 只喝一杯不算一餐
            for d in list(drinks) + [None]:
                items = [x for x in (m, s, d) if x is not None]
                kcal_sum = sum(x.kcal for x in items)
                protein_sum = sum(x.food.protein for x in items)
                fat_sum = sum(x.food.fat for x in items)
                sodium_sum = sum(x.food.sodium for x in items)
                price_sum = sum(x.menu.price for x in items)
                score = (
                    abs(kcal_sum - kcal) / max(kcal, 1) * 100
                    + abs(protein_sum - protein) / max(protein, 1) * 60
                    + abs(fat_sum - fat) / max(fat, 1) * 20
                    + max(0.0, sodium_sum - sodium_cap) * 0.02
                    + price_sum * 0.1          # 轻度价格压力，倾向高性价比
                )
                combos.append((score, (m, s, d)))
    combos.sort(key=lambda c: c[0])
    return combos[:topk]


def _assemble_day(rng, slot_combos, target: DailyTarget,
                  budget) -> tuple[dict, float]:
    """一轮重组：为每个餐位选一个组合，返回全天方案与评分。"""
    picked: set[int] = set()
    price_running = 0.0
    plan: dict[str, dict] = {}

    for slot in ("breakfast", "lunch", "dinner"):
        best_combo, best_pen = None, float("inf")
        for score, combo in slot_combos[slot]:
            ids = {id(x) for x in combo if x is not None}
            overlap = len(ids & picked)
            combo_price = sum(x.menu.price for x in combo if x is not None)
            pen = (
                score
                + overlap * 12.0                      # 全天去重惩罚
                + rng.uniform(0, 6.0)                 # 多样性扰动
            )
            if budget is not None:
                overflow = max(0.0, price_running + combo_price - budget)
                pen += overflow * 8.0                 # 预算软压力
            if pen < best_pen:
                best_pen, best_combo = pen, combo

        items = [x for x in best_combo if x is not None]
        picked.update(id(x) for x in items)
        price_running += sum(x.menu.price for x in items)
        plan[slot] = {
            "name": _MEAL_NAMES[slot],
            "items": [{"code": x.menu.code, "name": x.menu.name,
                       "price": x.menu.price, "kcal": x.kcal,
                       "protein": x.food.protein, "fat": x.food.fat,
                       "carbs": x.food.carbs, "sodium": x.food.sodium}
                      for x in items],
        }

    totals = _totals(plan)
    score = (
        abs(totals["kcal"] - target.kcal) / max(target.kcal, 1) * 100
        + abs(totals["protein"] - target.protein_g) / max(target.protein_g, 1) * 60
        + abs(totals["fat"] - target.fat_g) / max(target.fat_g, 1) * 25
        + max(0.0, totals["sodium"] - target.sodium_max_mg) / 100.0 * 10
        + (max(0.0, totals["price"] - budget) * 12 if budget is not None else 0.0)
    )
    return plan, score


def _totals(plan: dict) -> dict:
    t = {"kcal": 0.0, "protein": 0.0, "fat": 0.0, "carbs": 0.0,
         "sodium": 0.0, "price": 0.0}
    for meal in plan.values():
        for it in meal["items"]:
            for key in ("kcal", "protein", "fat", "carbs", "sodium", "price"):
                t[key] += it[key]
    return {k: round(v, 1) for k, v in t.items()}
