# 🍔 麦麦轻食官 McFit Coach

> 久坐、外卖、想控卡，但又想吃麦当劳？让 MCP 帮你「算着吃」。

麦麦轻食官是一个基于 **麦当劳中国 MCP** 的智能点餐助手：输入身体数据与目标（减脂 / 增肌 / 均衡），自动计算每日营养目标，基于麦当劳 **真实菜单与官方营养数据** 组合一日三餐，联动官方算价，最终生成一份可视化的营养报告页。

```text
身高体重目标 ──► 营养目标计算 ──► 真实菜单三餐组合 ──► 官方算价 ──► 可视化营养报告
     (Mifflin-St Jeor)      (麦当劳 MCP 菜单+营养)     (calculate-price)     (Chart.js)
```

![麦麦轻食官报告页演示](docs/samples/demo-report.gif)

## ✨ 核心特性

- **科学目标计算**：Mifflin-St Jeor 公式估算基础代谢，按活动系数与目标（减脂 -20% / 增肌 +15% / 均衡）折算每日热量、蛋白质、脂肪、碳水与钠上限
- **真实数据驱动**：158 个餐品的官方营养数据 + 实时门店菜单，绝不凭空编造餐品
- **两阶段组合算法**：每个餐位全枚举约 840 种「主餐 + 小食 + 饮品」组合（含轻食餐位）取 Top-40，再跨餐位 400 轮随机重组——单方案 80~200ms，实测热量误差 1~6%
- **官方算价联动**：组合结果直接送 `calculate-price` 真实算价，与菜单价分毫不差；支持用券容错试算
- **诚实输出**：快餐营养现实不粉饰——蛋白缺口建议补纯牛奶、钠超标红色警示、预算不可行时明确标注 `over_budget` 而不是硬塞
- **可视化报告**：一键生成 1080px 分享卡片式 HTML 报告（雷达图 / 环形图 / 三态进度条 / 营养师点评）

## 📦 安装

零第三方依赖，纯 Python 标准库（3.10+）：

```bash
git clone https://github.com/YOUR_GITHUB_USERNAME/mcd-fit-coach.git
cd mcd-fit-coach
```

## 🚀 使用

先到 [麦当劳 MCP 平台](https://open.mcd.cn/mcp) 注册并激活 Token，然后：

```bash
# 一条命令：拉营养库 → 查门店 → 组三餐 → 官方算价 → 生成报告
export MCD_MCP_TOKEN=你的Token
python src/main.py --sex male --weight 70 --height 175 --age 28 \
    --goal cut --budget 120 --seed 7 --report report.html
```

常用参数：

| 参数 | 说明 |
|---|---|
| `--sex` / `--weight` / `--height` / `--age` | 身体数据 |
| `--goal` | `cut` 减脂 / `bulk` 增肌 / `balance` 均衡 |
| `--budget` | 每日预算（元），软约束，超支会在报告中标出 |
| `--city` / `--keyword` / `--store-code` | 门店定位 |
| `--seed` | 固定随机种子，结果可复现 |
| `--report` | 同时生成可视化营养报告 HTML |
| `--bind` | ⚠️ 一键领取麦麦省可用券（真实入账），随后用券试算 |

也可以只从已有方案 JSON 生成报告：

```bash
python src/report.py --input docs/samples/demo-input.json -o report.html
```

## 📊 输出示例

真实运行的方案示例见 [`docs/samples/demo-report.html`](docs/samples/demo-report.html)（浏览器打开，图表需联网加载 Chart.js）与 [`docs/samples/demo-input.json`](docs/samples/demo-input.json)。

完整报告页截图（1200×1618）：

![报告页完整截图](docs/samples/report-full.png)

## 🎯 目标用户

- **健身减脂人群**：想控卡又馋麦当劳，需要「能吃的方案」而不是「不能吃清单」
- **久坐程序员**：一天三顿外卖，想让快餐吃得有依据
- **MCP / Agent 开发者**：把本项目当作麦当劳 MCP 的完整工程化参考实现（无状态客户端、营养库缓存、组合优化、报告生成）

## 🧱 项目结构

```text
mcd-fit-coach/
├── src/
│   ├── mcd_client.py    # 麦当劳 MCP 无状态客户端（握手/调用/JSON 提取）
│   ├── nutrition.py     # 营养知识库解析 + 每日目标计算
│   ├── meal_planner.py  # 菜单对齐 + 两阶段三餐组合算法
│   ├── coupon.py        # 领券 / 卡包 / 用券容错试算
│   ├── main.py          # CLI 全流程入口
│   └── report.py        # 可视化营养报告生成器
├── tests/test_core.py   # 核心链路回归测试
└── docs/                # 开发笔记与真实返回样本
```

## ⚠️ 免责声明

本项目为麦当劳程序员节创意开发大赛参赛作品，由参赛者独立开发，非麦当劳官方产品。项目输出仅供参考，不构成医疗、营养或其他专业建议；餐品信息、价格及供应状态以麦当劳官方渠道的实时结果为准。详见 [CONTEST_DECLARATION.md](CONTEST_DECLARATION.md)。

## 📄 License

[MIT](LICENSE)
