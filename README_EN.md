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
- **Official pricing**: the combo is priced through `calculate-price`, matching menu prices to the cent; `query-store-coupons` drives **coupon-to-item direct matching**, so a discounted price comes from a single pricing call (no blind trial)
- **Honest output**: no sugar-coating fast-food reality — protein gap suggests milk supplements, sodium overshoot turns red, infeasible budgets are flagged with `over_budget` instead of being forced
- **Visual report**: one command generates a 1080px shareable HTML report (radar chart / donut chart / five-axis tri-state progress bars / "nutritionist" notes / applied coupons), with a data-table fallback when Chart.js is offline

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
| `--no-coupon` | Skip coupons and price at the original price |
| `--bind` | ⚠️ Claim available coupons first (real account side effect), then use store-coupon direct matching |

You can also install it as a command:

```bash
pip install -e .
mcfc --sex male --weight 70 --height 175 --age 28 --goal cut --report report.html
```

You can also generate a report from an existing plan JSON:

```bash
python src/report.py --input docs/samples/demo-input.json -o report.html
```

## 📊 Example Output

See [`docs/samples/demo-report.html`](docs/samples/demo-report.html) for a real run (open in a browser; charts load Chart.js from CDN) and [`docs/samples/demo-input.json`](docs/samples/demo-input.json) for the input data.

Full-page report screenshot (1200×1783):

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
│   ├── coupon.py        # store coupon lookup + coupon-to-item direct pricing
│   ├── main.py          # CLI entry point for the full pipeline
│   └── report.py        # visual nutrition report generator
├── tests/test_core.py   # regression tests for the core pipeline (offline)
├── pyproject.toml       # zero-dependency packaging + `mcfc` console entry
├── .github/workflows/   # CI: Python 3.10-3.13 matrix + ruff
└── docs/                # dev notes and real API response samples
```

## 🧪 Development & Tests

Zero third-party dependencies; tests run fully offline (no token needed):

```bash
python tests/test_core.py     # nutrition / targets / alignment / planning / coupons / report
ruff check .                  # lint (optional: pip install ruff)
```

## ❓ Troubleshooting

| Symptom | Cause & fix |
|---|---|
| `HTTP 401` | Invalid/expired token — reactivate at [open.mcd.cn/mcp](https://open.mcd.cn/mcp) and refresh `MCD_MCP_TOKEN` |
| `600012 coupon not found` | The coupon code came from the wrong source — use the code from `query-store-coupons`, not from the wallet/claim result (see [MCP_INTEGRATION_EN.md](MCP_INTEGRATION_EN.md) finding 3) |
| No coupons / no discount | The store may have no applicable coupon right now — normal; `--bind` claims coupons first, `--no-coupon` skips coupons |
| Charts blank in the report | Chart.js loads from a CDN; when offline the report falls back to data tables (never blank) |
| Breakfast slot degrades | The menu is returned per time-of-day; there is no breakfast category at night — the tool prints a time note |

## 🧭 Design Boundary

- **Ordering is intentionally out of scope**: this project targets pre-meal decisions (what to eat, what it costs) and never calls `create-order`; you place the real order on official McDonald's channels (see [MCP_INTEGRATION_EN.md](MCP_INTEGRATION_EN.md))
- **Honest output**: when nutrition targets are unreachable in a fast-food setting (protein gap, sodium overshoot, tight budget), it says so rather than glossing over it
- **Official data is authoritative**: nutrition and menu come from live MCP responses, for reference only — not medical/nutritional advice
- **No `modification` support**: real calls show drinks expose only nutrition-neutral options (ice level); "sugar-free" is a separate SKU, not a modification — so it is intentionally not wired in

## 🗺 Roadmap

- [ ] Weekly plan (7 non-repeating days, cross-day balance)
- [ ] Auto-substitution on sodium overshoot (local search for lower sodium at equal calories)
- [ ] Store comparison (menu/price differences across stores in a city)
- [ ] Allergen / dietary filters (based on the nutrition table's `description` field)
- [ ] English report (`--lang en`)

## ⚠️ Disclaimer

This project is an entry to the McDonald's Programmer's Day Creative Development Contest, developed independently by the contestant. It is not an official McDonald's product. Output is for reference only and does not constitute medical, nutritional or other professional advice; menu items, prices and availability are subject to real-time results from official McDonald's channels. See [CONTEST_DECLARATION.md](CONTEST_DECLARATION.md) (official Chinese version).

## 📄 License

[MIT](LICENSE)
