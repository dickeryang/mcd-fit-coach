# MCP 集成说明

> 英文版：[MCP_INTEGRATION_EN.md](MCP_INTEGRATION_EN.md)

本项目基于 **麦当劳中国 MCP Server**（`https://mcp.mcd.cn`，Streamable HTTP + Bearer Token 鉴权）构建，真实调用了以下 Tool。

## 使用的 Tool 清单

| Tool | 用途 | 在项目中的位置 |
|---|---|---|
| `list-nutrition-foods` | 拉取全部餐品官方营养数据（千卡/蛋白/脂肪/碳水/钠/钙） | `main.py::get_foods`，本地缓存 24h |
| `query-nearby-stores` | 按城市+关键词查询附近门店，取营业中最近门店 | `main.py::pick_store` |
| `query-meals` | 拉取指定门店实时菜单（分类 + 餐品编码 + 现价） | `main.py::run` |
| `calculate-price` | 对三餐组合做官方逐品算价（金额单位：分） | `coupon.py::price_without_coupon` 等 |
| `available-coupons` | 查询当前可领取的优惠券列表 | `coupon.py::list_available_coupons` |
| `auto-bind-coupons` | 一键领取可用券（⚠️ 副作用，`--bind` 显式触发） | `coupon.py::bind_all_coupons` |
| `query-my-coupons` | 查询卡包已有券（展示用） | `coupon.py::list_my_coupons` |
| `query-my-account` | 查询积分账户 | 调试验证用 |
| `now-time-info` | 服务器时间（营业时段校验） | 调试验证用 |

## 核心调用流程

```text
① list-nutrition-foods ──► 解析 158 餐品营养库（本地缓存 24h）
② query-nearby-stores ───► 选定门店（city + keyword 必须同时传）
③ query-meals ───────────► 实时菜单，按名称归一化与营养库对齐（33+ 可规划项）
④ 本地两阶段组合算法 ─────► 生成一日三餐（无网络调用，纯本地优化）
⑤ calculate-price ───────► 三餐组合商品逐品官方算价，与规划价格互验
⑥ available-coupons / auto-bind-coupons / query-my-coupons ──► 用券试算（容错回退）
⑦ 生成可视化报告（本地渲染，不调用 MCP）
```

## 集成中的真实发现（对其他开发者有参考价值）

1. **服务端无 session 机制**：每次 `tools/call` 前先 `initialize` 即可，无需维护会话
2. **`query-nearby-stores` 必须 `city` + `keyword` 同时传**，只传 city 会报错
3. **券 ID 只在 `auto-bind-coupons` 的领取结果中返回**，`query-my-coupons` 仅含标题/价格/有效期
4. **`calculate-price` 用券必须 `couponId` + `couponCode` 成对传**（缺一报 600010）；营销券可能存在隐性使用条件（时段/门店类型/SKU 白名单），算价阶段可能报 600012，代码侧已做容错回退
5. **限流 600 次/分钟**，本项目单次全流程调用约 5-8 次，余量充足

## 业务价值

麦当劳 MCP 提供的是「点餐原子能力」（查菜单、算价、领券、下单），本项目把它组合成了一个新的决策场景：**面向健身人群的营养目标达成**——这是原子能力之上的一层业务封装，也是本项目区别于点餐/省钱类助手的核心价值。
