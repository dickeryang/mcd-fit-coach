# 🍔 McFit Coach (麦麦轻食官)

> Sedentary, living on takeout, watching your calories — but still craving McDonald's? Let MCP help you "eat it by the numbers".

[![CI](https://github.com/dickeryang/mcd-fit-coach/actions/workflows/ci.yml/badge.svg)](https://github.com/dickeryang/mcd-fit-coach/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-blue) ![License](https://img.shields.io/badge/license-MIT-green)

**English** | [简体中文](README.md)

McFit Coach is a smart meal-planning assistant built on **McDonald's China MCP**: enter your body stats and goal (cut / bulk / balance), and it computes your daily nutrition targets, assembles three meals a day from McDonald's **real menu and official nutrition data**, verifies the price with the official pricing tool, and generates a visual nutrition report.

```text
body stats & goal ──► daily targets ──► 3-meal combo (real menu) ──► official pricing ──► visual report
  (Mifflin-St Jeor)      (MCP menu + nutrition)   (calculate-price)        (Chart.js)
```

![McFit Coach report demo](docs/samples/demo-report.gif)

## ✨ Features

- **Science-based targets**: Mifflin-St Jeor BMR × activity factor, adjusted by goal (cut −20% / bulk +15% / balance) into daily calories, protein, fat, carbs and a sodium cap
- **Real data only**: official nutrition data for 158 menu items + live store menu — no invented dishes
- **Two-stage planning algorithm**: exhaustively enumerate ~840 "main + side + drink" combos per meal slot (light-meal slots included), keep Top-40, then re-assemble across slots over 400 randomized rounds — one plan in 80~200 ms, measured calorie error 1~6%
- **Official pricing**: the combo is priced through `calculate-price`, matching menu prices to the cent; coupon trial-pricing with graceful fallback
- **Honest output**: no sugar-coating fast-food reality — protein gap suggests milk supplements, sodium overshoot turns red, infeasible budgets are flagged with `over_budget` instead of being forced
- **Visual report**: one command generates a 1080px shareable HTML report (radar chart / donut chart / tri-state progress bars / "nutritionist" notes)

## 📦 Install

Zero third-party dependencies — pure Python standard library (3.10+):

```bash
git clone https://github.com/dickeryang/mcd-fit-coach.git
cd mcd-fit-coach
```

## 🚀 Usage

Register and activate a Token on the [McDonald's China MCP platform](https://open.mcd.cn/mcp) (China mainland phone number required), then:

```bash
# one command: nutrition DB → store → 3-meal plan → official pricing → report
export MCD_MCP_TOKEN=your_token
python src/main.py --sex male --weight 70 --height 175 --age 28 \
    --goal cut --budget 120 --seed 7 --report report.html
```

Common options:

| Option | Description |
|---|---|
| `--sex` / `--weight` / `--height` / `--age` | Body stats |
| `--goal` | `cut` (fat loss) / `bulk` (muscle gain) / `balance` |
| `--budget` | Daily budget in CNY (soft constraint; overshoot is flagged in the report) |
| `--city` / `--keyword` / `--store-code` | Store lookup |
| `--seed` | Fix the random seed for reproducible plans |
| `--report` | Also generate the visual nutrition report HTML |
| `--bind` | ⚠️ One-click claim of available coupons (real account side effect), then coupon trial-pricing |

You can also generate a report from an existing plan JSON:

```bash
python src/report.py --input docs/samples/demo-input.json -o report.html
```

## 📊 Example Output

See [`docs/samples/demo-report.html`](docs/samples/demo-report.html) for a real run (open in a browser; charts load Chart.js from CDN) and [`docs/samples/demo-input.json`](docs/samples/demo-input.json) for the input data.

Full-page report screenshot (1200×1618):

![Full report screenshot](docs/samples/report-full.png)

## 🎯 Target Users

- **Fitness & fat-loss folks**: want to eat McDonald's while staying on plan — "here's what you *can* eat", not a list of bans
- **Sedentary developers**: three takeout meals a day, want some evidence behind the fast food
- **MCP / Agent developers**: use this as a complete engineering reference for McDonald's MCP (stateless client, nutrition DB caching, combinatorial planning, report generation)

## 🧱 Project Structure

```text
mcd-fit-coach/
├── src/
│   ├── mcd_client.py    # stateless McDonald's MCP client (handshake / calls / JSON extraction)
│   ├── nutrition.py     # nutrition knowledge base + daily target calculation
│   ├── meal_planner.py  # menu alignment + two-stage meal planning algorithm
│   ├── coupon.py        # coupon claim / wallet / trial pricing with fallback
│   ├── main.py          # CLI entry point for the full pipeline
│   └── report.py        # visual nutrition report generator
├── tests/test_core.py   # regression tests for the core pipeline
└── docs/                # dev notes and real API response samples
```

## ⚠️ Disclaimer

This project is an entry to the McDonald's Programmer's Day Creative Development Contest, developed independently by the contestant. It is not an official McDonald's product. Output is for reference only and does not constitute medical, nutritional or other professional advice; menu items, prices and availability are subject to real-time results from official McDonald's channels. See [CONTEST_DECLARATION.md](CONTEST_DECLARATION.md) (official Chinese version).

## 📄 License

[MIT](LICENSE)
