# ETH Scalp Engine — 短线原生引擎

## 设计原则
- 消息驱动 > 趋势跟随
- 持仓 15-60 分钟，不做隔夜
- 止损 6 点，止盈 12 点，R ≥ 1:2
- 125x 逐仓，10U 本金级别

## 数据管道
| 数据 | 来源 | 方式 |
|------|------|------|
| ETH 实时价格 | OKX Ticker | urllib + 代理 |
| 费率/OI | OKX Public API | urllib |
| 恐惧贪婪 | alternative.me | urllib |
| 快讯/日历 | 金十 MCP | jin10_fetch.py |

## 命令
- `python scalp_monitor.py` — 跑一次，输出短线面板
- `python scalp_engine.py` — 引擎自测

## 原系统
长期系统在隔壁仓库: eth-contract-trader
