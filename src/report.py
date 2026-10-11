"""report.py — 麦麦轻食官 · 可视化营养报告页生成器。

输入: main.py 输出的方案 JSON（--input）
输出: 自包含 HTML 报告页（--output），Chart.js 雷达图 + 环形图 + 营养进度条

离线降级: Chart.js 由 CDN 加载，离线时自动显示数据表兜底，不留空白。

用法:
    python report.py --input ../docs/samples/e2e-plan.json -o report.html
"""

from __future__ import annotations

import argparse
import html
import json
from datetime import datetime
from pathlib import Path

GOAL_LABEL = {"cut": "减脂", "bulk": "增肌", "balance": "均衡"}
ACTIVITY_LABEL = {"sedentary": "久坐", "light": "轻度活动",
                  "moderate": "中度活动", "active": "高强度"}

# 生成报告所需的最小字段；缺失时给出可读报错而非 KeyError
_REQUIRED = ("target", "totals", "meals")


def _pct(actual: float, target: float) -> float:
    """实际值相对目标的百分比（上限 200%，防止进度条溢出）。"""
    if target <= 0:
        return 0.0
    return round(min(actual / target * 100, 200), 1)


def _radar_data(result: dict) -> dict:
    """五维雷达图数据：热量/蛋白/脂肪/碳水为达成率，钠为反向指标。"""
    t, tot = result["target"], result["totals"]
    return {
        "labels": ["热量", "蛋白质", "脂肪", "碳水", "钠(越低越好)"],
        "actual": [
            _pct(tot["kcal"], t["kcal"]),
            _pct(tot["protein"], t["protein_g"]),
            _pct(tot["fat"], t["fat_g"]),
            _pct(tot["carbs"], t["carbs_g"]),
            # 钠：达标率 = 上限/实际（超标时 <100）
            round(min(t["sodium_max_mg"] / max(tot["sodium"], 1) * 100, 200), 1),
        ],
        "target": [100, 100, 100, 100, 100],
    }


def _bar(item: float, label: str, target: float, unit: str,
         tone: str = "ok") -> str:
    """营养进度条：>=100% 绿色达成；钠/脂肪超标时红色警示。"""
    p = _pct(item, target)
    if tone == "reverse":          # 钠：越低越好
        cls = "good" if p <= 100 else "bad"
        text = f"{item:.0f}{unit} / 上限 {target:.0f}{unit}"
    else:
        cls = "good" if 80 <= p <= 120 else ("warn" if p < 80 else "bad")
        text = f"{item:.0f}{unit} / 目标 {target:.0f}{unit}"
    return f"""
    <div class="nutri-row">
      <div class="nutri-head"><span>{label}</span>
        <span class="nutri-val {cls}">{p}%</span></div>
      <div class="bar"><div class="bar-fill {cls}" style="width:{min(p, 100)}%"></div></div>
      <div class="nutri-sub">{text}</div>
    </div>"""


def _meal_card(slot: str, meal: dict) -> str:
    items_html = "".join(
        f'<div class="m-item"><span class="m-name">{html.escape(str(i["name"]))}</span>'
        f'<span class="m-meta">¥{i["price"]} · {i["kcal"]:.0f}kcal'
        f' · 蛋白{i["protein"]:.0f}g · 钠{i["sodium"]:.0f}mg</span></div>'
        for i in meal["items"]) or '<div class="m-item m-empty">（轻食：本餐不安排主餐）</div>'
    kcal = sum(i["kcal"] for i in meal["items"])
    price = sum(i["price"] for i in meal["items"])
    return f"""
    <div class="meal-card">
      <div class="meal-head"><span class="meal-slot">{html.escape(str(meal['name']))}</span>
        <span class="meal-sum">{kcal:.0f} kcal · ¥{price:.1f}</span></div>
      {items_html}
    </div>"""


def _coupon_block(result: dict) -> str:
    """已用优惠券信息块（无券时返回空串）。"""
    coupons = result.get("coupons") or []
    if not coupons:
        return ""
    rows = "".join(
        f'<div class="cp-item"><span class="cp-title">🎟 {html.escape(str(c.get("title", "")))}</span>'
        f'<span class="cp-meta">'
        + ("适用：" + html.escape("、".join(c.get("products") or [])) if c.get("products") else "")
        + (f' · 有效期 {html.escape(str(c["valid_range"]))}' if c.get("valid_range") else "")
        + '</span></div>'
        for c in coupons)
    return f"""
  <div class="card">
    <h2>🎟 已用优惠券</h2>
    {rows}
  </div>"""


def generate_report(result: dict) -> str:
    missing = [k for k in _REQUIRED if k not in result]
    if missing:
        raise ValueError(f"报告输入缺少字段: {', '.join(missing)}"
                         "（请用 main.py 的 -o 输出喂给 report.py）")
    t, tot = result["target"], result["totals"]
    profile = result.get("profile") or {}
    radar = _radar_data(result)

    # 洞察文案：蛋白缺口 / 钠超标 / 预算
    tips = []
    if tot["protein"] < t["protein_g"]:
        gap = t["protein_g"] - tot["protein"]
        tips.append(f"🥛 蛋白缺口 <b>{gap:.0f}g</b>：快餐食材蛋白密度有限，建议餐后补 1-2 盒纯牛奶（每盒约 8g 蛋白）")
    if tot["sodium"] > t["sodium_max_mg"]:
        over = tot["sodium"] - t["sodium_max_mg"]
        tips.append(f"🧂 钠超标 <b>{over:.0f}mg</b>：连续三顿汉堡类主食钠摄入偏高，次日建议选择沙拉/玉米杯类小食并多饮水")
    if result.get("over_budget"):
        tips.append("💰 预算提示：当前营养目标在快餐场景下难以压入预算，方案已按最接近预算优化，可适当上调预算")
    if not tips:
        tips.append("✅ 五项营养指标均在合理区间，方案可直接照单点餐")
    if result.get("time_note"):
        tips.insert(0, f"🕐 {html.escape(str(result['time_note']))}")

    kcal_per_meal = {
        m["name"]: sum(i["kcal"] for i in m["items"])
        for m in result["meals"].values()}

    price_block = f'<span class="price-main">¥{tot["price"]:.1f}</span>'
    if result.get("official_price"):
        off = f"官方算价 ¥{result['official_price']}"
        if result.get("discount"):
            off += f"（已优惠 ¥{result['discount']}）"
        price_block += f'<span class="price-official">{html.escape(off)}</span>'

    store = result.get("store") or {}
    store_html = (f'<div class="store">📍 {html.escape(str(store.get("storeName", "")))}'
                  f'{(" · " + html.escape(str(store["address"]))) if store.get("address") else ""}</div>'
                  if store.get("storeName") else "")

    profile_html = " · ".join(filter(None, [
        f"{'男' if profile.get('sex') == 'male' else '女'}"
        f" {profile.get('weight_kg', '?')}kg/{profile.get('height_cm', '?')}cm",
        f"{profile.get('age', '?')}岁",
        ACTIVITY_LABEL.get(profile.get("activity"), ""),
        GOAL_LABEL.get(profile.get("goal"), ""),
        (f"预算 ¥{profile['budget']}" if profile.get("budget") else ""),
    ]))

    # 离线兜底数据表（Chart.js 不可用时展示）
    radar_rows = "".join(
        f"<tr><td>{lbl}</td><td>{v}%</td></tr>"
        for lbl, v in zip(radar["labels"], radar["actual"]))
    donut_rows = "".join(
        f"<tr><td>{html.escape(str(k))}</td><td>{v:.0f} kcal</td></tr>"
        for k, v in kcal_per_meal.items())

    server_line = (f" · 服务器时间 {html.escape(str(result['generated_at']))}"
                   if result.get("generated_at") else "")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>麦麦轻食官 · 一日三餐营养报告</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         background: #f0f2f5; color: #1f2329; padding: 24px 0; }}
  .page {{ width: 1080px; max-width: 100%; margin: 0 auto; }}
  .card {{ background: #fff; border-radius: 16px; padding: 28px 32px;
          margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,.06); }}
  .hero {{ background: linear-gradient(135deg, #ffbc0d 0%, #ff8a00 100%); color: #fff; }}
  .hero h1 {{ font-size: 30px; letter-spacing: 1px; }}
  .hero .sub {{ margin-top: 8px; font-size: 15px; opacity: .95; }}
  .hero .store {{ margin-top: 10px; font-size: 14px; opacity: .9; }}
  h2 {{ font-size: 19px; margin-bottom: 18px; color: #1f2329; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
  .chart-box {{ position: relative; height: 320px; }}
  .chart-fallback {{ display: none; }}
  .chart-fallback table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  .chart-fallback td {{ padding: 8px 6px; border-bottom: 1px dashed #eef0f3; }}
  .chart-fallback td:last-child {{ text-align: right; color: #8a919f; }}
  .nutri-row {{ margin-bottom: 16px; }}
  .nutri-head {{ display: flex; justify-content: space-between; font-size: 15px; font-weight: 600; }}
  .nutri-val {{ font-size: 15px; }}
  .nutri-val.good {{ color: #16a34a; }}
  .nutri-val.warn {{ color: #d97706; }}
  .nutri-val.bad {{ color: #dc2626; }}
  .bar {{ height: 10px; background: #eef0f3; border-radius: 6px; margin: 6px 0 4px; overflow: hidden; }}
  .bar-fill {{ height: 100%; border-radius: 6px; }}
  .bar-fill.good {{ background: #16a34a; }}
  .bar-fill.warn {{ background: #d97706; }}
  .bar-fill.bad {{ background: #dc2626; }}
  .nutri-sub {{ font-size: 12.5px; color: #8a919f; }}
  .meal-card {{ border: 1px solid #eef0f3; border-radius: 12px; padding: 16px 20px; margin-bottom: 14px; }}
  .meal-head {{ display: flex; justify-content: space-between; margin-bottom: 10px; }}
  .meal-slot {{ font-size: 16px; font-weight: 700; color: #b45309; }}
  .meal-sum {{ font-size: 13.5px; color: #8a919f; }}
  .m-item {{ display: flex; justify-content: space-between; padding: 6px 0;
            border-top: 1px dashed #f0f2f5; font-size: 14.5px; }}
  .m-item:first-of-type {{ border-top: none; }}
  .m-name {{ font-weight: 600; }}
  .m-meta {{ color: #8a919f; font-size: 13px; }}
  .m-empty {{ color: #8a919f; }}
  .price-row {{ display: flex; align-items: baseline; gap: 16px; }}
  .price-main {{ font-size: 34px; font-weight: 800; color: #dc2626; }}
  .price-official {{ font-size: 15px; color: #16a34a; font-weight: 600; }}
  .tip {{ padding: 12px 16px; background: #fffbeb; border-left: 4px solid #f59e0b;
         border-radius: 0 10px 10px 0; font-size: 14.5px; margin-bottom: 10px; line-height: 1.6; }}
  .cp-item {{ display: flex; justify-content: space-between; gap: 12px;
             padding: 10px 0; border-bottom: 1px dashed #eef0f3; font-size: 14.5px; }}
  .cp-item:last-child {{ border-bottom: none; }}
  .cp-title {{ font-weight: 600; color: #b45309; }}
  .cp-meta {{ color: #8a919f; font-size: 13px; text-align: right; }}
  .footer {{ text-align: center; color: #a8b0bc; font-size: 12.5px; padding: 8px 0 24px; }}
  @media (max-width: 1120px) {{
    .page {{ width: 100%; padding: 0 16px; }}
    .grid {{ grid-template-columns: 1fr; }}
    .hero h1 {{ font-size: 24px; }}
  }}
</style>
</head>
<body>
<div class="page">

  <div class="card hero">
    <h1>🍔 麦麦轻食官 · 一日三餐营养报告</h1>
    <div class="sub">{profile_html}｜目标 {t['kcal']:.0f} kcal / 蛋白 {t['protein_g']:.0f}g</div>
    {store_html}
  </div>

  <div class="grid">
    <div class="card">
      <h2>🎯 营养达成雷达（100% = 目标线）</h2>
      <div class="chart-box"><canvas id="radar"></canvas>
        <div class="chart-fallback"><table>{radar_rows}</table></div>
      </div>
    </div>
    <div class="card">
      <h2>📊 关键指标</h2>
      {_bar(tot['kcal'], '热量', t['kcal'], 'kcal')}
      {_bar(tot['protein'], '蛋白质', t['protein_g'], 'g')}
      {_bar(tot['fat'], '脂肪', t['fat_g'], 'g')}
      {_bar(tot['carbs'], '碳水', t['carbs_g'], 'g')}
      {_bar(tot['sodium'], '钠', t['sodium_max_mg'], 'mg', tone='reverse')}
      <div class="nutri-row" style="margin-top:18px">
        <div class="nutri-head"><span>💰 全天合计</span></div>
        <div class="price-row">{price_block}</div>
      </div>
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <h2>🌅 三餐热量分布</h2>
      <div class="chart-box"><canvas id="donut"></canvas>
        <div class="chart-fallback"><table>{donut_rows}</table></div>
      </div>
    </div>
    <div class="card">
      <h2>📋 三餐明细</h2>
      {''.join(_meal_card(k, m) for k, m in result['meals'].items())}
    </div>
  </div>
{_coupon_block(result)}
  <div class="card">
    <h2>💡 营养师点评</h2>
    {''.join(f'<div class="tip">{x}</div>' for x in tips)}
  </div>

  <div class="footer">麦麦轻食官 McFit Coach · 数据来源：麦当劳中国 MCP（真实菜单与营养数据）·
    生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}{server_line}</div>
</div>

<script>
const radar = {json.dumps(radar, ensure_ascii=False)};
const donut = {json.dumps(kcal_per_meal, ensure_ascii=False)};

if (typeof Chart === 'undefined') {{
  // 离线：CDN 未加载，退化为数据表
  document.querySelectorAll('.chart-fallback').forEach(el => el.style.display = 'block');
  document.querySelectorAll('.chart-box canvas').forEach(el => el.style.display = 'none');
}} else {{
  new Chart(document.getElementById('radar'), {{
    type: 'radar',
    data: {{
      labels: radar.labels,
      datasets: [
        {{ label: '实际达成%', data: radar.actual,
           backgroundColor: 'rgba(255,138,0,.25)', borderColor: '#ff8a00',
           pointBackgroundColor: '#ff8a00', borderWidth: 2 }},
        {{ label: '目标线', data: radar.target,
           backgroundColor: 'rgba(22,163,74,.06)', borderColor: '#16a34a',
           borderDash: [6, 4], pointRadius: 0, borderWidth: 1.5 }},
      ],
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      scales: {{ r: {{ min: 0, suggestedMax: 130,
        ticks: {{ stepSize: 25, color: '#8a919f', backdropColor: 'transparent' }},
        grid: {{ color: '#eef0f3' }}, angleLines: {{ color: '#eef0f3' }},
        pointLabels: {{ font: {{ size: 14 }}, color: '#1f2329' }} }} }},
      plugins: {{ legend: {{ position: 'bottom' }} }},
    }},
  }});

  new Chart(document.getElementById('donut'), {{
    type: 'doughnut',
    data: {{
      labels: Object.keys(donut),
      datasets: [{{ data: Object.values(donut).map(v => Math.round(v)),
        backgroundColor: ['#ffbc0d', '#ff8a00', '#e2582b'],
        borderColor: '#fff', borderWidth: 3 }}],
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{ legend: {{ position: 'bottom' }},
        tooltip: {{ callbacks: {{ label: c => `${{c.label}}: ${{c.raw}} kcal` }} }} }},
    }},
  }});
}}
</script>
</body>
</html>"""


def main(argv=None):
    p = argparse.ArgumentParser(description="生成麦麦轻食官营养报告页")
    p.add_argument("--input", required=True, help="main.py 输出的方案 JSON")
    p.add_argument("-o", "--output", default="report.html", help="输出 HTML 路径")
    args = p.parse_args(argv)

    try:
        result = json.loads(Path(args.input).read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise SystemExit(f"读取输入失败: {e}")
    if not isinstance(result, dict):
        raise SystemExit("输入 JSON 顶层必须是对象")
    result.setdefault("profile", {})
    try:
        html_out = generate_report(result)
    except ValueError as e:
        raise SystemExit(f"生成报告失败: {e}") from e
    Path(args.output).write_text(html_out, encoding="utf-8")
    print(f"报告已生成: {args.output}")


if __name__ == "__main__":
    main()
