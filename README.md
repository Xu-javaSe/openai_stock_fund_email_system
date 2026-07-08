# 股票 + 基金观察邮箱系统

这是一个统一的 GitHub 自动邮件项目：每天自动抓取龙虎榜和行情数据，生成股票观察邮件；下午 14:00 的邮件会额外加入 ETF 和场外基金观察池。

> 仅用于学习、研究和观察，不构成任何股票、基金、证券或金融产品的买卖建议。

## 核心规则

- 股票只保留当日涨幅 `5% - 10%` 的龙虎榜股票。
- 涨幅低于 5% 不进入观察池。
- 涨幅高于 10% 不进入观察池。
- 20% 大涨或涨停票不会出现在邮件主体里。
- 龙虎榜综合权重：同花顺 `70%`，东方财富 `30%`。
- 历史行情自动抓取真实数据，用于趋势、压力位、回撤和波动判断。

## 邮件时间

GitHub Actions 使用 UTC 时间，已经换算为北京时间：

| 北京时间 | UTC | 邮件内容 |
|---|---:|---|
| 12:00 | 04:00 | 股票观察邮件 |
| 14:00 | 06:00 | 股票 + ETF + 场外基金综合邮件 |

## 功能

股票部分：

- 同花顺 + 东方财富龙虎榜自动抓取
- 5%-10% 涨幅硬过滤
- 推荐比例
- 趋势状态
- 压力位状态
- 风险等级
- 操作提示
- 板块联动
- 股票分组池：低吸观察池、突破确认池、只看不追池、风险回避池

基金部分：

- 只在 14:00 综合邮件中出现
- 包含 ETF 和场外基金
- 从股票强方向映射到相关基金
- 基金趋势、压力位、回撤、波动分析
- 基金分组池：趋势观察池、回调低吸池、高位谨慎池、暂不参与池

记忆功能：

- `data/state.json` 记录近期强方向、股票和基金连续入池情况
- GitHub Actions 运行后会尝试自动提交最新记忆状态

## GitHub Secrets

进入仓库：

```text
Settings -> Secrets and variables -> Actions -> New repository secret
```

添加：

| Secret | 说明 |
|---|---|
| `SMTP_HOST` | SMTP服务器，例如 `smtp.qq.com` |
| `SMTP_PORT` | 常用 `465` 或 `587` |
| `SMTP_USER` | 发件邮箱 |
| `SMTP_PASSWORD` | 邮箱 SMTP 授权码 |
| `MAIL_TO` | 收件邮箱 |
| `MAIL_FROM` | 可选，默认等于 `SMTP_USER` |
| `MAIL_SUBJECT_PREFIX` | 可选，邮件标题前缀 |

QQ 邮箱示例：

```text
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_USER=你的QQ邮箱
SMTP_PASSWORD=QQ邮箱SMTP授权码
MAIL_TO=你的收件邮箱
```

## 本地测试

只生成文件，不发送邮件：

```bash
python scripts/send_report.py --date 2026-07-08 --mode stock --dry-run --output output_test_stock
python scripts/send_report.py --date 2026-07-08 --mode full --dry-run --output output_test_full
```

输出文件：

```text
output/email_preview.html
output/dashboard.html
output/stock_scores.csv
output/fund_scores.csv
output/report.json
```

## 手动运行 GitHub Actions

在 GitHub Actions 页面选择：

```text
Stock Fund Observation Email -> Run workflow
```

可选输入：

```text
trade_date: 2026-07-08
report_mode: stock 或 full
```

## 重要说明

本系统输出的是观察清单和风险提示，不是买入或卖出指令。实际交易需要结合个人风险承受能力、市场环境和合规要求独立判断。
