# D0 API 探查笔记（2026-10-10）

> 环境：Token 已激活，直连 `https://mcp.mcd.cn`（Streamable HTTP，Bearer Token）。
> 本文件是开发期的接口事实记录，原始返回样本见 `samples/`。
> ⚠️ 真实 Token 只存在于本地 `~/.workbuddy/mcp.json`，严禁提交到任何仓库。

## 0. 协议层结论

- 服务器 `mcd-mcp v1.0.0`，协议 `2025-03-26` 正常握手。
- 服务端**不返回 mcp-session-id**：每次 `tools/call` 前先发一次 `initialize` 即可（无状态调用可行）。
- 返回格式：`content[].text`，内容为「字段说明 + Original Response（内嵌 JSON 字符串）」。
- 解析要点：取 text 中最后一个 `{"success":...` 起始的 JSON 对象。
- 限流：600 次/分钟（未触发）。

## 1. now-time-info（无参）✅

返回毫秒时间戳 + 格式化时间。用于"早餐/午餐/夜市"时段判断（门店预约时段文本与当前时段相关）。

## 2. list-nutrition-foods（无参）✅ 核心数据源

- **160 个餐品**，一次性全量返回。
- `data` 是字符串，格式为类 CSV：首行 `[160]{productName,nutritionDescription,energyKj,energyKcal,protein,fat,carbohydrate,sodium,calcium}:`，随后每行一个餐品，逗号分隔。
- 数值单位：energyKj/energyKcal（千焦/千卡）、protein/fat/carbohydrate/sodium/calcium（克/毫克，样本中钠为 mg 量级、钙为 mg）。
- 注意：存在重复行（如"小杯玉米杯"出现两次）和 `nutritionDescription=null`，解析时按 productName 去重、null 处理为缺省。
- 样本：`samples/nutrition-raw.txt`（约 8.9KB）。
- **开发策略**：本地缓存全量营养表，避免重复调用。

## 3. query-nearby-stores（beType=1, searchType=2, city+keyword）✅

- **必须 city + keyword 同时传**（只传 city 报 600058"城市名或者关键词不能为空"；searchType=1 收藏列表为空报 600050）。
- 入参：`{beType: 1|5, searchType: 2, city: "上海市", keyword: "麦当劳"}`。
- 返回字段：`storeCode`（工具入参）、`beCode`（到店自取场景不传）、`distance`（米）、`businessStatus/StartTime/EndTime`、`reservation` + `reservationTimeOptions`（早餐/午餐/下午茶/夜市/宵夜时段文本）。
- 样例返回上海门店 5+ 家（账号默认位置上海）。

## 4. query-meals（storeCode, orderType=1, beType=1）✅ 核心数据源

- 返回约 26KB：`data.categories[]`（分类 + meals[].code/tags）+ `data.meals` map（code → 详情：name/image/currentPrice 等）。
- 菜单与营养表需**按名称模糊对齐**（菜单 name 与营养表 productName 大体一致，但有营销名差异，如套餐组合名）。开发时建立别名映射表。
- 样本：`samples/query-meals-raw.txt`。

## 5. available-coupons（无参）✅

- 返回麦麦省可领券列表：标题/状态/图片 URL。样本含"巧克力味厚松饼猪柳蛋套餐"等多张可领券。
- 领券用 `auto-bind-coupons`（**有副作用**：真实入账，开发验证时执行一次即可）。
- 样本：`samples/available-coupons-raw.txt`。

## 6. query-my-account（无参）✅

返回积分账户：accountId / accumulativePoint / availablePoint / currency 等，全部 string 类型。

## 7. 待探查（D1 开发时验证）

| 工具 | 待确认点 |
|---|---|
| `query-meal-detail` | 套餐组成与可替换选项结构（orderType=1 时**不要传 beCode**，传了报错） |
| `calculate-price` | items 数组完整字段（code/quantity/couponId/couponCode/modification） |
| `auto-bind-coupons` / `query-my-coupons` | 领券后券的 couponId/couponCode 格式，与 calculate-price 的对齐方式 |
| `create-order` | 到店自取下单最小字段集（仅验证到返回支付链接，不实际支付） |

## 8. 对 MVP 的影响

- 营养表 160 项全量可得 → 三餐组合算法可行性确认 ✅
- 门店需 city+keyword → 报告页/README 示例用"上海市"即可复现 ✅
- 菜单价格在 query-meals 中已有 currentPrice → 算价前可先做本地预算筛选 ✅
