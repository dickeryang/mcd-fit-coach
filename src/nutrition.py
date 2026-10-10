"""nutrition.py — 营养知识库与每日营养目标计算。

数据来源：MCP 工具 `list-nutrition-foods`（全量 160 餐品，类 CSV 内嵌于 JSON）。
字段顺序: productName, nutritionDescription, energyKj, energyKcal,
          protein, fat, carbohydrate, sodium, calcium

本模块职责：
1. 解析 MCP 返回文本 → Food 列表（去重、类型清洗、启发式分类）
2. Mifflin-St Jeor 基础代谢 + 活动系数 → TDEE
3. 按目标（减脂/增肌/均衡）生成每日热量与三大营养素目标
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

# --------------------------------------------------------------------- #
# 数据模型
# --------------------------------------------------------------------- #

@dataclass(frozen=True)
class Food:
    """单个餐品的营养记录（能量单位统一为千卡，质量单位 g，钠/钙 mg）。"""
    name: str
    kcal: float
    protein: float
    fat: float
    carbs: float
    sodium: float
    calcium: float
    category: str = "其他"          # 启发式分类：主食/小食/饮品/甜品/早餐
    description: str = ""


@dataclass
class DailyTarget:
    """每日营养目标。"""
    kcal: float
    protein_g: float
    fat_g: float
    carbs_g: float
    sodium_max_mg: float = 2000.0

    def as_dict(self) -> dict:
        return {
            "kcal": round(self.kcal), "protein_g": round(self.protein_g),
            "fat_g": round(self.fat_g), "carbs_g": round(self.carbs_g),
            "sodium_max_mg": round(self.sodium_max_mg),
        }


# --------------------------------------------------------------------- #
# 解析 MCP 返回
# --------------------------------------------------------------------- #

_HEADER_RE = re.compile(r"^\[\d+\]\{.*\}:")


def parse_nutrition_text(text: str) -> list[Food]:
    """解析 `list-nutrition-foods` 的 text 返回 → Food 列表（按名称去重）。

    兼容两种入参：完整 MCP text（含说明与内嵌 JSON），或已是 data 字符串本身。
    行格式: `名称,描述,kJ,kcal,蛋白,脂肪,碳水,钠,钙`（描述可为 null）。
    """
    data_str = _extract_data_string(text)
    foods: dict[str, Food] = {}
    for line in data_str.split("\n"):
        line = line.strip()
        if not line or _HEADER_RE.match(line):
            continue
        parts = line.split(",")
        if len(parts) < 9:
            continue
        head, tail = parts[:-7], parts[-7:]
        name, desc = head[0].strip(), ",".join(head[1:]).strip()
        try:
            kj, kcal, protein, fat, carbs, sodium, calcium = (float(x) for x in tail)
        except ValueError:
            continue  # 脏行跳过
        if name in foods:            # 重复行去重（保留首条）
            continue
        desc = "" if desc.lower() == "null" else desc
        foods[name] = Food(name=name, kcal=kcal, protein=protein, fat=fat,
                           carbs=carbs, sodium=sodium, calcium=calcium,
                           category=categorize(name), description=desc)
    return list(foods.values())


def _extract_data_string(text: str) -> str:
    """从 MCP text 中提取 data 字段（内嵌 JSON 里的字符串）。"""
    m = re.search(r'\{"success":.*', text, re.S)
    if not m:
        return text  # 已是 data 字符串
    snippet = m.group(0)
    end = snippet.rfind("}")
    while end > 0:
        try:
            obj = json.loads(snippet[:end + 1])
            return obj.get("data") or ""
        except json.JSONDecodeError:
            end = snippet.rfind("}", 0, end)
    return text


# --------------------------------------------------------------------- #
# 启发式分类（优先级从上到下，命中即返回）
# --------------------------------------------------------------------- #

_CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    # 注意顺序：主食必须先于小食（"鸡腿堡"含"鸡腿"）
    ("主食", ("堡", "卷", "巨无霸", "麦香鸡", "麦香鱼", "安格斯", "板烧",
             "不素之霸", "鳕鱼", "双层吉士", "汉堡包")),
    ("早餐", ("麦满分", "粥", "早安", "炒双蛋", "脆香油条")),
    ("小食", ("薯条", "鸡翅", "麦辣翅", "鸡块", "麦乐鸡", "鸡排", "鸡球", "脆薯",
             "薯饼", "油条", "玉米杯", "苹果片", "香肠", "V翅", "脆汁鸡", "鸡腿",
             "沙拉", "芝士条", "薯")),
    ("甜品", ("新地", "麦旋风", "冰淇淋", "圆筒", "派", "奶冻", "爆珠", "拉明顿",
             "阿芙佳朵", "松饼")),
    ("饮品", ("可乐", "雪碧", "咖啡", "美式", "拿铁", "奶铁", "红茶", "绿茶", "抹茶",
             "牛奶", "豆浆", "果汁", "苹果汁", "柠檬", "雪冰", "怡泉", "纯悦",
             "麦旋酷", "卡布奇诺", "玛奇朵", "黑巧", "燕麦奶", "朱古力", "零度")),
]


def categorize(name: str) -> str:
    for cat, keywords in _CATEGORY_RULES:
        if any(k in name for k in keywords):
            return cat
    return "其他"


# --------------------------------------------------------------------- #
# 每日目标计算
# --------------------------------------------------------------------- #

ACTIVITY_FACTORS = {
    "sedentary": 1.2,    # 久坐（程序员默认）
    "light": 1.375,      # 每周轻度运动 1-3 次
    "moderate": 1.55,    # 每周中度运动 3-5 次
    "active": 1.725,     # 每周高强度 6-7 次
}

GOALS = ("cut", "bulk", "balance")


def bmr_mifflin(sex: str, weight_kg: float, height_cm: float, age: int) -> float:
    """Mifflin-St Jeor 基础代谢（kcal）。sex: 'male' / 'female'。"""
    base = 10.0 * weight_kg + 6.25 * height_cm - 5.0 * age
    return base + (5.0 if sex == "male" else -161.0)


def daily_target(sex: str, weight_kg: float, height_cm: float, age: int,
                 activity: str = "sedentary", goal: str = "cut") -> DailyTarget:
    """按身体数据与目标生成每日营养目标。

    - cut:     热量 -20%，蛋白 1.8 g/kg，脂肪占总热量 25%
    - bulk:    热量 +10%，蛋白 2.0 g/kg，脂肪占总热量 25%
    - balance: 热量维持，  蛋白 1.5 g/kg，脂肪占总热量 30%
    碳水 = 剩余热量 / 4；钠上限固定 2000mg（中国膳食指南成人建议量级）。
    """
    if goal not in GOALS:
        raise ValueError(f"goal 必须是 {GOALS} 之一")
    factor = ACTIVITY_FACTORS.get(activity)
    if factor is None:
        raise ValueError(f"activity 必须是 {list(ACTIVITY_FACTORS)} 之一")

    tdee = bmr_mifflin(sex, weight_kg, height_cm, age) * factor
    if goal == "cut":
        kcal = tdee * 0.80
        protein = 1.8 * weight_kg
        fat_ratio = 0.25
    elif goal == "bulk":
        kcal = tdee * 1.10
        protein = 2.0 * weight_kg
        fat_ratio = 0.25
    else:
        kcal = tdee
        protein = 1.5 * weight_kg
        fat_ratio = 0.30

    fat = kcal * fat_ratio / 9.0
    carbs = max((kcal - protein * 4.0 - fat * 9.0) / 4.0, 0.0)
    return DailyTarget(kcal=kcal, protein_g=protein, fat_g=fat, carbs_g=carbs)
