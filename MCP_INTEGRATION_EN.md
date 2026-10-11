# MCP Integration

> English version of [MCP_INTEGRATION.md](MCP_INTEGRATION.md) (Chinese). The Chinese file is the authoritative contest submission; this translation is provided for international readers.

This project is built on the **McDonald's China MCP Server** (`https://mcp.mcd.cn`, Streamable HTTP + Bearer Token auth) and makes real calls to the following tools.

## Configuring in WorkBuddy (verified)

In the connectors tab (Custom connector → Configure MCP), use this shape (`type` is
`streamablehttp`; get a Token from [open.mcd.cn/mcp](https://open.mcd.cn/mcp) and never
commit it):

```json
{
  "mcpServers": {
    "mcd-mcp": {
      "type": "streamablehttp",
      "url": "https://mcp.mcd.cn",
      "headers": { "Authorization": "Bearer <YOUR_MCD_MCP_TOKEN>" }
    }
  }
}
```

When running this repo from the CLI, pass the token via the environment variable
`MCD_MCP_TOKEN`.

## Tools Used

| Tool | Purpose | Where in the project |
|---|---|---|
| `list-nutrition-foods` | Fetch official nutrition data for all menu items (kcal / protein / fat / carbs / sodium / calcium) | `main.py::get_foods`, cached locally for 24 h |
| `query-nearby-stores` | Find nearby stores by city + keyword; pick the nearest | `main.py::pick_store` |
| `query-meals` | Fetch the live menu of a store (categories + item codes + current prices) | `main.py::get_menu`, cached locally for 1 h |
| `query-store-coupons` | **Store-scoped usable coupons (valid coupon codes + applicable item codes)** | `coupon.py::query_store_coupons` |
| `calculate-price` | Official per-item pricing of the combo (amounts in cents) | `coupon.py::price_without_coupon` / `price_with_store_coupons` |
| `now-time-info` | Server time (time-of-day note, e.g. breakfast availability) | `main.py::server_time` |
| `auto-bind-coupons` | One-click claim of available coupons (⚠️ side effect, gated behind `--bind`) | `coupon.py::bind_all_coupons` |
| `query-my-coupons` | List coupons in the wallet (**display only**, no coupon codes) | `coupon.py::list_my_coupons` |
| `available-coupons` | List claimable coupons | `coupon.py::list_available_coupons` |
| `query-my-account` | Points account query | used during integration testing |

## Core Call Flow

```text
① list-nutrition-foods ──► parse ~160-item nutrition DB (local cache, 24 h)
② query-nearby-stores ───► pick a store (city + keyword must both be passed)
③ query-meals ───────────► live menu, aligned with the nutrition DB by normalized names
④ local two-stage planner ─► build the 3-meal day plan (pure local optimization, no network)
⑤ query-store-coupons ───► usable coupons (codes + applicable item codes)
   calculate-price ───────► coupon-to-item matching, then a single pricing call
⑥ now-time-info ──────────► time-of-day note
⑦ render the visual report (local, no MCP calls)
```

## Real-world Findings (useful for other developers)

1. **The server is stateless**: no `mcp-session-id` is returned — a fresh `initialize` before each `tools/call` is all it takes
2. **`query-nearby-stores` requires both `city` and `keyword`**; passing only `city` errors out
3. **Coupon codes must come from `query-store-coupons`**: the code returned by the
   `auto-bind-coupons` claim result fails pricing with `600012 coupon not found`; only the
   store/order-scoped code is redeemable. Officially, `query-my-coupons` does **not**
   validate against store/channel and does not guarantee usability for the current order
4. **`calculate-price` requires `couponId` + `couponCode` as a pair** (missing either returns 600010); amounts are in **cents**; the response returns `takeWayList` for order pickup options
5. **`query-store-coupons` returns coupons + codes + applicable item codes in one call**, enabling **coupon-to-item direct matching** and cutting pricing down to a single call
6. **Rate limit is 600 calls/min**; one full pipeline run makes ~6-9 calls, leaving ample headroom

## Design Boundary: why this project does not call `create-order`

This project focuses on **pre-meal decisions** (what to eat, how much it costs) and
deliberately does not call `create-order`:

- **Responsibility boundary**: ordering involves real payment and pickup; it is left to the user on official McDonald's channels to avoid placing orders on their behalf
- **Contract difference**: `create-order` additionally needs `takeWayCode` (taken from the `takeWayList[].code` returned by `calculate-price`, required for orderType=1). This project stops at pricing, so the parameter is not needed
- If a "one-tap order" feature is added later, `takeWayList` is already parsed from the pricing result and can be reused

## Business Value

The McDonald's MCP exposes atomic ordering capabilities (menu, pricing, coupons, ordering). This project composes them into a new decision scenario — **nutrition-goal attainment for fitness-minded customers** — a business layer above the atoms, which is what distinguishes it from ordering/savings-style assistants.
