# 📈 Stock Trader AI - AI辅助股票交易工具

一个 Python 命令行工具，用于 **记录交易、统计分析、复盘回归、AI预测**，支持 A股/港股/美股多市场。

## ✨ 功能特性

- 📝 **交易记录** — 记录买入/卖出操作，支持 CSV 导入导出
- 📊 **统计分析** — 胜率、盈亏比、最大回撤、夏普比率等
- 📈 **行情数据** — 实时行情、K线、分时、财务报表（基于 stock-data）
- ⭐ **自选股/收藏列表** — 关注感兴趣的股票，一键查看所有自选股实时行情
- 🔄 **复盘回归** — 按日/周/月生成交易复盘报告
- 🎨 **数据可视化** — K线图、收益曲线、持仓分布图
- 🔮 **AI 预测** — ML (RandomForest + XGBoost) + DL (LSTM + Transformer) 涨跌预测
- 🧠 **LLM 分析** — 大语言模型综合四维（技术+基本+资金+消息面）深度分析报告
- 🔔 **实时预警** — 14种条件预警（价格/涨跌幅/RSI/MACD/KDJ/布林带/均线等）
- 👀 **实时看盘** — 自动刷新行情 + 预警检测，支持自选股监控
- 📈 **策略回测** — 7种内置策略回测引擎，多策略对比，完整绩效报告+可视化图表

## 📦 安装

```bash
# 进入项目目录
cd stock-trader-ai

# 创建虚拟环境（推荐）
python -m venv venv
venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt

# 安装为命令行工具（开发模式）
pip install -e .
```

## 🚀 快速开始

```bash
# 记录一笔交易
stock-ai trade add --code sh600519 --action buy --price 1800.5 --quantity 100 --reason "底部放量突破"

# 查看交易记录
stock-ai trade list

# 查看持仓
stock-ai portfolio show

# 添加自选股
stock-ai star sh600519 --note "长期关注"

# 查看自选股列表（带实时行情）
stock-ai stars

# 获取实时行情
stock-ai market quote sh600519

# 获取K线数据
stock-ai market kline sh600519 --period day --count 20

# 统计分析
stock-ai analysis summary

# AI 预测
stock-ai predict sh600519      # 综合预测报告
stock-ai scan                  # 扫描自选股信号排名

# 预警监控
stock-ai alert-add sh600519 price_above -t 1900   # 价格突破1900提醒
stock-ai alert-add sz000985 macd_cross -r          # MACD金叉提醒(可重复)
stock-ai alert-list                                 # 查看预警规则
stock-ai alert-check                                # 立即检测一次
stock-ai watch                                      # 实时看盘(自选股)

# 可视化图表
stock-ai chart pnl          # 收益曲线
stock-ai chart kline sh600519  # K线图

# 回测引擎
stock-ai bt sh600519                     # 默认MACD策略回测
stock-ai bt sh600519 -s rsi -d 365 -g   # RSI策略回测365天+出图
stock-ai bt-list                         # 查看可用策略
stock-ai bt-compare sh600519             # 7个策略全量对比
```

## 📁 项目结构

```
stock-trader-ai/
├── app/
│   ├── cli.py              # CLI 入口
│   ├── models/             # 数据模型 (交易/持仓/自选/预警)
│   ├── db/                 # 数据库层
│   ├── services/           # 业务逻辑 (交易/持仓/自选/预警/行情/回测)
│   ├── data/               # 数据获取（stock-data 封装）
│   ├── ai/                 # AI 预测（ML + DL 模型 + LLM 分析）
│   └── visualization/      # 可视化图表 (K线/收益曲线/回测权益曲线)
├── data/                   # 本地数据缓存
├── config.yaml             # 全局配置
├── requirements.txt        # 依赖
└── setup.py                # 安装配置
```

## 🛠 技术栈

- **CLI**: typer + rich
- **数据库**: SQLite + SQLAlchemy
- **数据源**: stock-data CLI（A股/港股/美股）
- **分析**: pandas + numpy
- **可视化**: matplotlib + plotly
- **AI**: scikit-learn + xgboost + pytorch (可选)

## 📋 支持的市场

| 市场 | 代码格式 | 示例 |
|------|---------|------|
| 沪市A股 | sh + 6位 | sh600519（贵州茅台）|
| 深市A股 | sz + 6位 | sz000001（平安银行）|
| 港股 | hk + 5位 | hk00700（腾讯控股）|
| 美股 | us + 代码 | usAAPL（苹果）|

## 📄 License

MIT
