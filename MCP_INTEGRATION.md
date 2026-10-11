# MCP 集成说明

> 英文版：[MCP_INTEGRATION_EN.md](MCP_INTEGRATION_EN.md)

本项目基于 **麦当劳中国 MCP Server**（`https://mcp.mcd.cn`，Streamable HTTP + Bearer Token 鉴权）构建，真实调用了以下 Tool。

## 在 WorkBuddy 中配置（实测可用）

连接器页签【自定义连接器 → 配置 MCP】填入以下结构（`type` 用 `streamablehttp`，
Token 从 [open.mcd.cn/mcp](https://open.mcd.cn/mcp) 申请，勿提交到仓库）：

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

命令行使用本仓库时则走环境变量：`export MCD_MCP_TOKEN=你的Token`。

## 使用的 Tool 清单

| Tool | 用途 | 在项目中的位置 |
|---|---|---|
| `list-nutrition-foods` | 拉取全部餐品官方营养数据（千卡/蛋白/脂肪/碳水/钠/钙） | `main.py::get_foods`，本地缓存 24h |
| `query-nearby-stores` | 按城市+关键词查询附近门店，取最近一家 | `main.py::pick_store` |
| `query-meals` | 拉取指定门店实时菜单（分类 + 餐品编码 + 现价） | `main.py::get_menu`，本地缓存 1h |
| `query-store-coupons` | **查询门店维度可用券（含有效券码 + 适用商品编码）** | `coupon.py::query_store_coupons` |
| `calculate-price` | 对三餐组合做官方逐品算价（金额单位：分） | `coupon.py::price_without_coupon` / `price_with_store_coupons` |
| `now-time-info` | 服务器时间（生成时段提示，如早餐可用性） | `main.py::server_time` |
| `auto-bind-coupons` | 一键领取可用券（⚠️ 副作用，`--bind` 显式触发） | `coupon.py::bind_all_coupons` |
| `query-my-coupons` | 查询卡包已有券（**仅展示**，不含券码） | `coupon.py::list_my_coupons` |
| `available-coupons` | 查询可领取券列表 | `coupon.py::list_available_coupons` |
| `query-my-account` | 积分账户查询 | 调试验证用 |

## 核心调用流程

```text
① list-nutrition-foods ──► 解析约 160 餐品营养库（本地缓存 24h）
② query-nearby-stores ───► 选定门店（city + keyword 必须同时传）
③ query-meals ───────────► 实时菜单，按名称归一化与营养库对齐
④ 本地两阶段组合算法 ─────► 生成一日三餐（无网络调用，纯本地优化）
⑤ query-store-coupons ──► 门店可用券（券码 + 适用商品编码）
   calculate-price ──────► 券-商品直配后单次算价，与规划价格互验
⑥ now-time-info ─────────► 时段提示
⑦ 生成可视化报告（本地渲染，不调用 MCP）
```

## 集成中的真实发现（对其他开发者有参考价值）

1. **服务端无 session 机制**：每次 `tools/call` 前先 `initialize` 即可，无需维护会话
2. **`query-nearby-stores` 必须 `city` + `keyword` 同时传**，只传 city 会报错
3. **券码必须取自 `query-store-coupons`**：`auto-bind-coupons` 领取结果里的券码
   算价会报 `600012 未找到优惠券`；门店/订单维度接口返回的才是可核销码。
   官方亦明确 `query-my-coupons` 不做门店/渠道校验，不承诺可用于当前订单
4. **`calculate-price` 用券必须 `couponId` + `couponCode` 成对传**（缺一报 600010）；
   金额单位是**分**；返回 `takeWayList` 供下单取餐方式使用
5. **`query-store-coupons` 一次返回「可用券 + 券码 + 适用商品编码」**：可做
   **券-商品直配**，把定价从「每券 × 每商品位盲试」压缩为 1 次算价调用
6. **限流 600 次/分钟**，本项目单次全流程调用约 6-9 次，余量充足

## 设计边界：为什么本项目不接 `create-order`

本项目的定位是**餐前决策**（吃什么、多少钱），刻意不调用 `create-order`（下单）：

- **责任边界**：下单涉及真实支付与取餐，交由用户在麦当劳官方渠道确认，避免代下单风险
- **契约差异**：`create-order` 需额外传 `takeWayCode`（值取自 `calculate-price` 返回的
  `takeWayList[].code`，到店场景必传）；本项目只到算价为止，因此不需要该参数
- 若后续要做「一键下单」，`takeWayList` 已在算价结果中解析，可直接复用

## 业务价值

麦当劳 MCP 提供的是「点餐原子能力」（查菜单、算价、领券、下单），本项目把它组合成了一个新的决策场景：**面向健身人群的营养目标达成**——这是原子能力之上的一层业务封装，也是本项目区别于点餐/省钱类助手的核心价值。
