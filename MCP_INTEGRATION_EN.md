# MCP Integration

> English version of [MCP_INTEGRATION.md](MCP_INTEGRATION.md) (Chinese). The Chinese file is the authoritative contest submission; this translation is provided for international readers.

This project is built on the **McDonald's China MCP Server** (`https://mcp.mcd.cn`, Streamable HTTP + Bearer Token auth) and makes real calls to the following tools.

## Tools Used

| Tool | Purpose | Where in the project |
|---|---|---|
| `list-nutrition-foods` | Fetch official nutrition data for all menu items (kcal / protein / fat / carbs / sodium / calcium) | `main.py::get_foods`, cached locally for 24 h |
| `query-nearby-stores` | Find nearby open stores by city + keyword | `main.py::pick_store` |
| `query-meals` | Fetch the live menu of a store (categories + item codes + current prices) | `main.py::get_menu`, cached locally for 1 h |
| `calculate-price` | Official per-item pricing for a meal combo (amounts in cents) | `coupon.py::price_without_coupon` etc. |
| `available-coupons` | List currently claimable coupons | `coupon.py::list_available_coupons` |
| `auto-bind-coupons` | One-click claim of all available coupons (⚠️ side effect, gated behind `--bind`) | `coupon.py::bind_all_coupons` |
| `query-my-coupons` | List coupons already in the wallet (display only) | `coupon.py::list_my_coupons` |
| `query-my-account` | Points account query | used during integration testing |
| `now-time-info` | Server time (business-hours validation) | used during integration testing |

## Core Call Flow

```text
① list-nutrition-foods ──► parse 158-item nutrition DB (local cache, 24 h)
② query-nearby-stores ───► pick a store (city + keyword must both be passed)
③ query-meals ───────────► live menu, aligned with the nutrition DB by normalized names (33+ plannable items)
④ local two-stage planner ─► build the 3-meal day plan (pure local optimization, no network)
⑤ calculate-price ───────► official per-item pricing of the combo, cross-checked against planner prices
⑥ available-coupons / auto-bind-coupons / query-my-coupons ──► coupon trial pricing (fault-tolerant fallback)
⑦ render the visual report (local, no MCP calls)
```

## Real-world Findings (useful for other developers)

1. **The server is stateless**: no `mcp-session-id` is returned — a fresh `initialize` before each `tools/call` is all it takes
2. **`query-nearby-stores` requires both `city` and `keyword`**; passing only `city` errors out
3. **Coupon IDs are only returned in the `auto-bind-coupons` claim result**; `query-my-coupons` only contains title/price/validity
4. **`calculate-price` requires `couponId` + `couponCode` as a pair** (missing either returns 600010); marketing coupons may carry hidden conditions (time window / store type / SKU whitelist) and can return 600012 at the pricing stage — the code falls back gracefully
5. **Rate limit is 600 calls/min**; one full pipeline run makes ~5-8 calls, leaving ample headroom

## Business Value

The McDonald's MCP exposes atomic ordering capabilities (menu, pricing, coupons, ordering). This project composes them into a new decision scenario — **nutrition-goal attainment for fitness-minded customers** — a business layer above the atoms, which is what distinguishes it from ordering/savings-style assistants.
