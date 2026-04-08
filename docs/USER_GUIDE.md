# Stock Trader AI 使用手册

> AI辅助股票交易记录与分析工具，帮你记录每一笔交易、跟踪持仓、复盘分析。

---

## 目录

- [快速开始](#快速开始)
- [新手完整流程](#新手完整流程)
- [命令速查表](#命令速查表)
- [缩写速查卡片](#缩写速查卡片)
- [详细命令说明](#详细命令说明)
  - [初始化](#初始化)
  - [搜索股票](#搜索股票)
  - [查看行情](#查看行情)
  - [买入交易](#买入交易)
  - [卖出交易](#卖出交易)
  - [查看持仓](#查看持仓)
  - [交易记录管理](#交易记录管理)
  - [统计分析](#统计分析)
  - [可视化图表](#可视化图表)
  - [AI 预测](#ai-预测)
  - [预警监控](#预警监控)
  - [实时看盘](#实时看盘)
- [数据说明](#数据说明)
- [常见问题](#常见问题)

---

## 快速开始

### 1. 安装

```bash
cd stock-trader-ai
pip install -e .
```

### 2. 初始化

```bash
stock-ai init
```

### 3. 开始使用

```bash
stock-ai search 茅台                    # 搜索股票 (缩写: sc)
stock-ai quote sh600519                  # 查看行情 (缩写: q)
stock-ai star sh600519 --note "长期关注"  # 添加自选股 (缩写: sa)
stock-ai stars                           # 查看自选股列表 (缩写: ss)
stock-ai buy sh600519 1465.75 100        # 买入 (缩写: b)
stock-ai show                            # 查看持仓 (缩写: w)
```

> 💡 所有命令都有缩写，比如 `stock-ai sc 茅台`、`stock-ai q sh600519`、`stock-ai ss`、`stock-ai b sh600519 1465.75 100`、`stock-ai w`

---

## 新手完整流程

作为初次使用者，推荐按以下流程操作：

### 第一步：初始化项目

```bash
stock-ai init
```

创建数据库和数据目录，**只需运行一次**。

### 第二步：搜索你关注的股票

```bash
stock-ai search 茅台
stock-ai search 腾讯
stock-ai search 比亚迪
```

找到股票代码，比如 `sh600519`（贵州茅台）、`hk00700`（腾讯控股）。

> **代码格式说明**：
> - A股上海：`sh` + 6位代码，如 `sh600519`
> - A股深圳：`sz` + 6位代码，如 `sz000858`
> - 港股：`hk` + 5位代码，如 `hk00700`
> - 美股：`us` + 代码，如 `usAAPL`

### 第三步：查看实时行情，决定是否买入

```bash
stock-ai quote sh600519              # 实时价格
stock-ai kline sh600519              # 最近K线走势
stock-ai finance sh600519            # 财务数据
stock-ai news sh600519               # 最新新闻
stock-ai fund sh600519               # 资金流向
```

### 第三步半：把感兴趣的股票加入自选

```bash
stock-ai star sh600519 --note "茅台，长期关注白酒龙头"
stock-ai star hk00700 --note "腾讯，观察游戏业务"
stock-ai stars                           # 查看所有自选股的实时行情
```

> 💡 自选股列表会显示所有关注股票的**实时行情、涨跌幅、成交量、市盈率**，方便你每天快速浏览关注的股票动态。

### 第四步：买入，记录交易

```bash
stock-ai buy sh600519 1465.75 100 -n "贵州茅台" -r "底部放量突破"
```

参数说明：
- `sh600519` — 股票代码（必填）
- `1465.75` — 成交价格（必填）
- `100` — 成交数量/股（必填）
- `-n "贵州茅台"` — 股票名称（可选，方便识别）
- `-r "底部放量突破"` — 交易理由（可选，复盘时很有用）

### 第五步：查看持仓

```bash
stock-ai show
```

会自动联动实时行情，显示**浮动盈亏**和**盈亏率**。

### 第六步：卖出

```bash
stock-ai sell sh600519 1520.00 100 -n "贵州茅台" -r "到达目标价止盈"
```

### 第七步：复盘分析

```bash
stock-ai trades                      # 回顾所有交易记录
stock-ai summary                     # 胜率、盈亏比等核心指标
stock-ai monthly                     # 按月统计盈亏
stock-ai ranking                     # 哪只股票赚最多/亏最多
stock-ai drawdown                    # 最大回撤分析
```

### 第八步：生成图表（可选）

```bash
stock-ai chart-pnl                   # 收益曲线图
stock-ai chart-kline sh600519        # K线图
stock-ai chart-portfolio             # 持仓分布饼图
stock-ai chart-monthly               # 月度盈亏柱状图
stock-ai chart-winloss               # 胜负统计图
```

### 日常使用循环

```
搜索/看行情 → 加自选 → 设预警 → 看盘监控 → 买入 → 看持仓 → 卖出 → 复盘分析
     ↑                                                              |
     └──────────────────────────────────────────────────────────────┘
```

---

## 命令速查表

所有命令都支持**缩写**，日常使用只需记几个字母即可。

| 场景 | 完整命令 | 缩写 | 示例 |
|------|---------|------|------|
| 初始化 | `stock-ai init` | — | `stock-ai init` |
| 搜索股票 | `stock-ai search <关键词>` | `sc` | `stock-ai sc 茅台` |
| 实时行情 | `stock-ai quote <代码>` | `q` | `stock-ai q sh600519` |
| 多股行情 | `stock-ai quote <代码1>,<代码2>` | `q` | `stock-ai q sh600519,hk00700` |
| K线数据 | `stock-ai kline <代码>` | `k` | `stock-ai k sh600519` |
| 财务数据 | `stock-ai finance <代码>` | `f` | `stock-ai f sh600519` |
| 公司简况 | `stock-ai profile <代码>` | `pf` | `stock-ai pf sh600519` |
| 资金流向 | `stock-ai fund <代码>` | `fd` | `stock-ai fd sh600519` |
| 新闻资讯 | `stock-ai news <代码>` | `n` | `stock-ai n sh600519` |
| 筹码分布 | `stock-ai chip <代码>` | — | `stock-ai chip sh600519` |
| 买入 | `stock-ai buy <代码> <价格> <数量>` | `b` | `stock-ai b sh600519 1465 100` |
| 卖出 | `stock-ai sell <代码> <价格> <数量>` | `s` | `stock-ai s sh600519 1520 100` |
| 查看持仓 | `stock-ai show` | `w` | `stock-ai w` |
| 重建持仓 | `stock-ai rebuild` | `rb` | `stock-ai rb` |
| **⭐ 自选股** | | | |
| 查看自选股 | `stock-ai stars` | `ss` | `stock-ai ss` |
| 添加自选股 | `stock-ai star <代码>` | `sa` | `stock-ai sa sh600519 -n "长期关注"` |
| 取消收藏 | `stock-ai unstar <代码>` | `sd` | `stock-ai sd sh600519` |
| 更新备注 | `stock-ai watchlist note <代码> <备注>` | — | `stock-ai watchlist note sh600519 "新备注"` |
| 交易记录 | `stock-ai trades` | `t` | `stock-ai t` |
| 删除记录 | `stock-ai del-trade <ID>` | `dt` | `stock-ai dt 3 -y` |
| 统计摘要 | `stock-ai summary` | `sm` | `stock-ai sm` |
| 月度盈亏 | `stock-ai monthly` | `mo` | `stock-ai mo` |
| 盈亏排名 | `stock-ai ranking` | `rk` | `stock-ai rk` |
| 最大回撤 | `stock-ai drawdown` | `dd` | `stock-ai dd` |
| 收益曲线 | `stock-ai chart-pnl` | `c-pnl` | `stock-ai c-pnl` |
| K线图 | `stock-ai chart-kline <代码>` | `c-k` | `stock-ai c-k sh600519` |
| 持仓饼图 | `stock-ai chart-portfolio` | `c-pf` | `stock-ai c-pf` |
| 月度图 | `stock-ai chart-monthly` | `c-mo` | `stock-ai c-mo` |
| 胜负图 | `stock-ai chart-winloss` | `c-wl` | `stock-ai c-wl` |
| **🔮 AI 预测** | | | |
| AI 预测 | `stock-ai predict <代码>` | `p` | `stock-ai p sh600519` |
| 预测+LLM | `stock-ai predict <代码> --llm` | — | `stock-ai p sh600519 --llm` |
| 扫描自选股 | `stock-ai scan` | — | `stock-ai scan` |
| 训练模型 | `stock-ai train-ai <代码>` | — | `stock-ai train-ai sh600519` |
| 查看模型 | `stock-ai ai models` | — | `stock-ai ai models` |
| **🧠 LLM 分析** | | | |
| LLM 深度分析 | `stock-ai analyze <代码>` | `a` | `stock-ai a sh600519` |
| 测试 LLM | `stock-ai test-llm` | — | `stock-ai test-llm` |
| **🔔 预警监控** | | | |
| 添加预警 | `stock-ai alert-add <代码> <条件>` | `al-a` | `stock-ai alert-add sh600519 price_above -t 1900` |
| 查看预警 | `stock-ai alert-list` | `al-l` | `stock-ai al-l` |
| 删除预警 | `stock-ai alert-del <ID>` | `al-d` | `stock-ai al-d 1 -y` |
| 启停预警 | `stock-ai alert-toggle <ID>` | `al-t` | `stock-ai al-t 1` |
| 重置预警 | `stock-ai alert-reset <ID>` | `al-r` | `stock-ai al-r 1` |
| 立即检测 | `stock-ai alert-check` | `al-c` | `stock-ai al-c` |
| 触发历史 | `stock-ai alert-history` | `al-h` | `stock-ai al-h` |
| 条件类型 | `stock-ai alert-types` | `al-tp` | `stock-ai al-tp` |
| **👀 实时看盘** | | | |
| 看盘模式 | `stock-ai watch` | `wa` | `stock-ai wa` |
| 指定股票 | `stock-ai watch -c <代码>` | `wa` | `stock-ai wa -c sh600519,sz000985` |
| 查看帮助 | `stock-ai --help` | — | `stock-ai --help` |

---

## 缩写速查卡片

> 只需记住这几个字母，效率翻倍！

### 高频操作（每天用）

```
stock-ai b  sh600519 1465 100     # 买入 (buy)
stock-ai s  sh600519 1520 100     # 卖出 (sell)
stock-ai w                        # 看持仓 (watch)
stock-ai q  sh600519              # 看行情 (quote)
stock-ai sc 茅台                  # 搜股票 (search)
stock-ai t                        # 交易记录 (trades)
stock-ai ss                       # 自选股列表 (stars)
stock-ai p  sh600519              # AI 预测 (predict)
stock-ai a  sh600519              # LLM 深度分析 (analyze)
```

### 行情研究

```
stock-ai k  sh600519              # K线 (kline)
stock-ai f  sh600519              # 财务 (finance)
stock-ai pf sh600519              # 简况 (profile)
stock-ai fd sh600519              # 资金 (fund)
stock-ai n  sh600519              # 新闻 (news)
```

### 复盘分析

```
stock-ai sm                       # 统计摘要 (summary)
stock-ai mo                       # 月度盈亏 (monthly)
stock-ai rk                       # 排名 (ranking)
stock-ai dd                       # 回撤 (drawdown)
```

### 可视化

```
stock-ai c-pnl                    # 收益曲线图
stock-ai c-k   sh600519           # K线图
stock-ai c-pf                     # 持仓饼图
stock-ai c-mo                     # 月度盈亏图
stock-ai c-wl                     # 胜负统计图
```

### 其他

```
stock-ai dt 3 -y                  # 删除交易 (del-trade)
stock-ai rb                       # 重建持仓 (rebuild)
```

### AI 预测

```
stock-ai p  sh600519              # 预测 (predict)
stock-ai p  sh600519 --dl         # 含深度学习预测
stock-ai scan                     # 扫描自选股信号
stock-ai train-ai sh600519        # 手动训练模型
```

### 预警监控

```
stock-ai al-a sh600519 price_above -t 1900  # 添加预警 (alert-add)
stock-ai al-l                               # 预警列表 (alert-list)
stock-ai al-c                               # 立即检测 (alert-check)
stock-ai al-d 1 -y                          # 删除预警 (alert-del)
stock-ai al-t 1                             # 启停预警 (alert-toggle)
stock-ai al-r 1                             # 重置预警 (alert-reset)
stock-ai al-h                               # 触发历史 (alert-history)
stock-ai al-tp                              # 条件类型 (alert-types)
stock-ai wa                                 # 实时看盘 (watch)
stock-ai wa -c sh600519,sz000985 -i 15      # 指定股票看盘
```

### 完整缩写映射表

| 缩写 | 全称 | 助记 |
|------|------|------|
| `b` | buy | **b**uy 买入 |
| `s` | sell | **s**ell 卖出 |
| `t` | trades | **t**rades 记录 |
| `dt` | del-trade | **d**el-**t**rade 删除 |
| `w` | show | **w**atch 看持仓 |
| `rb` | rebuild | **r**e**b**uild 重建 |
| `sc` | search | **s**ear**c**h 搜索 |
| `q` | quote | **q**uote 行情 |
| `k` | kline | **k**line K线 |
| `f` | finance | **f**inance 财务 |
| `pf` | profile | **p**ro**f**ile 简况 |
| `fd` | fund | **f**un**d** 资金 |
| `n` | news | **n**ews 新闻 |
| `sm` | summary | **s**u**m**mary 统计 |
| `mo` | monthly | **mo**nthly 月度 |
| `rk` | ranking | **r**an**k**ing 排名 |
| `dd` | drawdown | **d**raw**d**own 回撤 |
| `c-pnl` | chart-pnl | **c**hart 收益 |
| `c-k` | chart-kline | **c**hart **K**线 |
| `c-pf` | chart-portfolio | **c**hart 持仓 |
| `c-mo` | chart-monthly | **c**hart 月度 |
| `c-wl` | chart-winloss | **c**hart 胜负 |
| `p` | predict | **p**redict 预测 |
| `al-a` | alert-add | **al**ert-**a**dd 添加预警 |
| `al-l` | alert-list | **al**ert-**l**ist 预警列表 |
| `al-d` | alert-del | **al**ert-**d**el 删除预警 |
| `al-t` | alert-toggle | **al**ert-**t**oggle 启停 |
| `al-r` | alert-reset | **al**ert-**r**eset 重置 |
| `al-c` | alert-check | **al**ert-**c**heck 检测 |
| `al-h` | alert-history | **al**ert-**h**istory 历史 |
| `al-tp` | alert-types | **al**ert-**t**y**p**es 类型 |
| `wa` | watch | **wa**tch 看盘 |

---

## 详细命令说明

### 初始化

```bash
stock-ai init
```

创建 SQLite 数据库和所需的数据目录。**首次使用前必须执行**。

---

### 搜索股票

```bash
stock-ai search <关键词>
```

支持按名称、代码、拼音搜索。覆盖 A股、港股、美股。

**示例：**

```bash
stock-ai search 茅台        # 按名称
stock-ai search 600519      # 按代码
stock-ai search AAPL         # 美股代码
```

---

### 查看行情

#### 实时行情

```bash
stock-ai quote <代码>
stock-ai quote sh600519,hk00700    # 同时查多只
```

显示：现价、涨跌幅、涨跌额、今开、最高、最低、成交量、市盈率。

#### K线数据

```bash
stock-ai kline <代码> [选项]
```

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `--period / -p` | 周期：day/week/month/m5/m15/m30/m60 | day |
| `--count / -c` | 获取数量 | 20 |
| `--adjust / -a` | 复权：qfq(前复权)/hfq(后复权) | qfq |

**示例：**

```bash
stock-ai kline sh600519                    # 最近20天日K
stock-ai kline sh600519 -p week -c 10      # 最近10周周K
stock-ai kline sh600519 -p m30 -c 50       # 最近50根30分钟K线
```

#### 其他行情数据

```bash
stock-ai finance sh600519                  # 财务摘要
stock-ai finance sh600519 -t lrb           # 利润表
stock-ai finance sh600519 -t zcfz          # 资产负债表
stock-ai finance sh600519 -t xjll          # 现金流量表
stock-ai profile sh600519                  # 公司简况
stock-ai fund sh600519                     # 资金流向(默认20天)
stock-ai fund sh600519 -d 60               # 资金流向(60天)
stock-ai news sh600519                     # 新闻资讯
stock-ai chip sh600519                     # 筹码分布
```

---

### 自选股/收藏列表

把感兴趣的股票加入自选，方便每天快速查看行情动态。

#### 添加自选股

```bash
stock-ai star <代码> [选项]
```

| 选项 | 说明 | 示例 |
|------|------|------|
| `-n / --note` | 关注备注/理由 | `-n "底部形态，观察突破"` |

**示例：**

```bash
stock-ai star sh600519 --note "茅台，长期关注"
stock-ai sa sz000985 -n "观察反弹"         # 使用缩写
```

> 添加时会自动从行情接口获取股票名称。

#### 查看自选股列表

```bash
stock-ai stars
stock-ai ss          # 缩写
```

显示所有关注股票的：**代码、名称、现价、涨跌幅、涨跌额、最高、最低、成交量、市盈率、备注**。

#### 取消收藏

```bash
stock-ai unstar <代码>
stock-ai sd sh600519     # 缩写
```

#### 更新备注

```bash
stock-ai watchlist note <代码> <备注>
```

**示例：**

```bash
stock-ai watchlist note sh600519 "等回调到1400再加仓"
```

---

### 买入交易

```bash
stock-ai buy <代码> <价格> <数量> [选项]
```

| 选项 | 说明 | 示例 |
|------|------|------|
| `-n / --name` | 股票名称 | `-n "贵州茅台"` |
| `-r / --reason` | 交易理由 | `-r "底部放量突破"` |
| `-s / --strategy` | 所用策略 | `-s "趋势跟踪"` |
| `--time` | 交易时间 | `--time "2026-04-08 09:35:00"` |

**示例：**

```bash
# 最简写法
stock-ai buy sh600519 1465.75 100

# 完整写法
stock-ai buy sh600519 1465.75 100 -n "贵州茅台" -r "MACD金叉" -s "技术分析"

# 补录历史交易
stock-ai buy sh600519 1400.00 200 -n "贵州茅台" --time "2026-03-15 10:30:00"
```

> 手续费和印花税会**自动计算**（手续费万2.5，卖出印花税千1）。

---

### 卖出交易

```bash
stock-ai sell <代码> <价格> <数量> [选项]
```

用法与 `buy` 完全相同。卖出时会自动计算盈亏。

```bash
stock-ai sell sh600519 1520.00 100 -n "贵州茅台" -r "目标价止盈"
```

---

### 查看持仓

```bash
stock-ai show
```

显示所有持仓股票的：代码、名称、持仓数量、成本价、现价、市值、浮动盈亏、盈亏率、今日涨跌。

底部汇总：持仓数量、总成本、总市值、浮动盈亏、已实现盈亏、总盈亏。

> 现价数据来自 `stock-data` 实时行情。

#### 重建持仓

```bash
stock-ai rebuild
```

如果持仓数据异常，可根据所有交易记录重新计算持仓。

---

### 交易记录管理

#### 查看记录

```bash
stock-ai trades                          # 查看最近20条
stock-ai trades -l 50                    # 查看最近50条
stock-ai trades -c sh600519              # 只看茅台的记录
```

#### 删除记录

```bash
stock-ai del-trade 3                     # 删除ID=3的记录（会确认）
stock-ai del-trade 3 -y                  # 跳过确认直接删除
```

#### 导入导出（通过子命令组）

```bash
stock-ai trade export                            # 导出为CSV
stock-ai trade export -f ./my_trades.csv         # 指定路径
stock-ai trade import ./my_trades.csv            # 从CSV导入
```

---

### 统计分析

#### 交易统计摘要

```bash
stock-ai summary
stock-ai summary --start 2026-01-01 --end 2026-03-31     # 指定时间段
stock-ai summary -m A                                     # 只看A股
```

输出指标：
- **交易概况**：总次数、买入/卖出次数、已平仓数、活跃期间
- **胜率分析**：胜率、盈亏比、盈/亏/平笔数
- **盈亏统计**：总盈利、总亏损、平均盈利/亏损、最大单笔盈/亏
- **费用**：手续费、印花税、净利润
- **持仓周期**：平均持仓天数、最长持仓

#### 月度盈亏

```bash
stock-ai monthly
stock-ai monthly --start 2026-01-01
```

按月统计：交易次数、盈亏笔数、胜率、总盈亏、平均盈亏。

#### 股票盈亏排名

```bash
stock-ai ranking
```

按股票维度排名：哪只赚最多、哪只亏最多。

#### 最大回撤

```bash
stock-ai drawdown
```

计算最大回撤金额、回撤率、峰值日期、谷底日期。

---

### 可视化图表

所有图表自动保存到 `data/charts/` 目录。

```bash
stock-ai chart-pnl                       # 收益曲线（累计盈亏随时间变化）
stock-ai chart-kline sh600519            # K线图
stock-ai chart-kline sh600519 -c 120     # 120根K线
stock-ai chart-portfolio                 # 持仓分布饼图
stock-ai chart-monthly                   # 月度盈亏柱状图
stock-ai chart-winloss                   # 胜负统计图
```

---

### AI 预测

AI 预测模块利用机器学习和深度学习模型，基于技术指标分析股票未来走势。

#### 预测股票走势

```bash
stock-ai predict <代码> [选项]
stock-ai p sh600519              # 缩写
```

| 选项 | 说明 | 默认 |
|------|------|------|
| `--dl` | 同时使用 DL (LSTM) 模型 | 关闭 |

输出内容：
- **综合信号**：看涨/看跌/震荡 + 星级评分
- **多模型对比**：XGBoost、RandomForest（可选 LSTM）的独立预测
- **关键因子**：MACD 金叉/死叉、RSI 超买超卖、均线排列等
- **特征重要性排名**：模型认为最重要的技术指标
- **技术指标快照**：当前各项技术指标数值

> ⚡ 首次预测某只股票时会**自动训练**模型（需要几秒），后续预测直接加载已有模型。

#### 扫描自选股

```bash
stock-ai scan [选项]
```

批量扫描所有自选股，输出**信号排名表**：按综合评分从高到低排序，方便快速发现机会。

#### 手动训练模型

```bash
stock-ai train-ai <代码> [选项]
```

| 选项 | 说明 |
|------|------|
| `--dl` | 同时训练 DL (LSTM) 模型 |

手动训练会显示详细的训练结果：样本数、准确率、标签分布等。

#### 查看已有模型

```bash
stock-ai ai models
stock-ai ai models -c sh600519    # 只看某只股票的模型
```

#### 预测原理简述

```
K线数据 (最近800天日K)
  ↓
特征工程 (40+技术指标)
  ├─ 趋势: MA5/10/20/60, EMA, MACD
  ├─ 动量: RSI, KDJ, ROC, WR
  ├─ 波动: 布林带, ATR
  └─ 成交量: OBV, 量比
  ↓
模型预测
  ├─ ML: RandomForest + XGBoost
  └─ DL: LSTM + Attention (可选)
  ↓
融合评分 → 综合信号 + 关键因子
```

> ⚠️ **风险提示**：AI 预测仅供参考，不构成投资建议。模型基于历史数据，无法预知突发事件。

---

### 预警监控

预警模块支持 14 种条件类型，覆盖价格、涨跌幅、技术指标等多维度监控。

#### 支持的预警条件

| 类型代码 | 名称 | 需要阈值 | 单位 |
|----------|------|----------|------|
| `price_above` | 价格突破 | ✓ | 元 |
| `price_below` | 价格跌破 | ✓ | 元 |
| `change_above` | 涨幅超过 | ✓ | % |
| `change_below` | 跌幅超过 | ✓ | % |
| `volume_above` | 成交量超过 | ✓ | 万手 |
| `turnover_above` | 换手率超过 | ✓ | % |
| `rsi_above` | RSI超买 | ✓ | — |
| `rsi_below` | RSI超卖 | ✓ | — |
| `macd_cross` | MACD金叉 | ✗ | — |
| `macd_dead` | MACD死叉 | ✗ | — |
| `kdj_cross` | KDJ金叉 | ✗ | — |
| `boll_upper` | 突破布林上轨 | ✗ | — |
| `boll_lower` | 跌破布林下轨 | ✗ | — |
| `ma_bull` | 均线多头排列 | ✗ | — |

> 💡 使用 `stock-ai alert-types` 可随时查看所有支持的条件类型。

#### 添加预警

```bash
stock-ai alert-add <代码> <条件> [选项]
```

| 选项 | 说明 | 示例 |
|------|------|------|
| `-t / --threshold` | 阈值（价格/百分比） | `-t 1900` |
| `-r / --repeat` | 可重复触发（默认单次触发后自动停止） | `-r` |
| `-n / --note` | 备注 | `-n "茅台突破前高"` |

**示例：**

```bash
# 价格预警
stock-ai alert-add sh600519 price_above -t 1900 -n "突破1900元"
stock-ai alert-add sz000985 price_below -t 18.5 -n "跌破支撑位"

# 涨跌幅预警
stock-ai alert-add sh600519 change_above -t 5 -n "涨超5%止盈"
stock-ai alert-add sz000985 change_below -t 5 -r -n "跌超5%（可重复）"

# 技术指标预警
stock-ai alert-add sz000985 macd_cross -r -n "MACD金叉买入信号"
stock-ai alert-add sh600519 rsi_above -t 70 -n "RSI超买注意风险"
stock-ai alert-add sz000985 rsi_below -t 30 -n "RSI超卖关注反弹"
stock-ai alert-add sh600519 boll_upper -n "突破布林上轨"
stock-ai alert-add sz000985 kdj_cross -n "KDJ金叉"
stock-ai alert-add sh600519 ma_bull -n "均线多头排列"
```

#### 管理预警

```bash
stock-ai alert-list                      # 查看所有预警规则
stock-ai alert-list --active             # 仅显示启用的
stock-ai alert-list -c sz000985          # 按股票代码过滤
stock-ai alert-toggle 1                  # 暂停/启用预警
stock-ai alert-reset 1                   # 重置已触发的预警（重新监控）
stock-ai alert-del 1                     # 删除预警
stock-ai alert-del 1 -y                  # 跳过确认直接删除
```

#### 检测预警

```bash
stock-ai alert-check                     # 立即检测一次所有活跃预警
```

获取实时行情数据，逐条检测所有活跃的预警规则。触发的预警会高亮显示。

#### 触发历史

```bash
stock-ai alert-history                   # 查看所有触发历史
stock-ai alert-history -c sz000985       # 按股票过滤
stock-ai alert-history --id 1            # 按预警规则ID过滤
stock-ai alert-history -l 50             # 显示最近50条
```

#### 预警模式说明

- **单次触发（默认）**：预警触发一次后自动标记为"已触发"状态，不再重复提醒
- **重复触发（-r）**：每次检测到条件满足都会触发，适合持续监控的场景

---

### 实时看盘

看盘模式会定时自动刷新行情数据，并同时执行预警检测。

```bash
stock-ai watch [选项]
```

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `-c / --codes` | 股票代码（逗号分隔） | 自选股列表 |
| `-i / --interval` | 刷新间隔（秒） | 30 |
| `--alert-only` | 仅监控预警，不显示行情表 | 关闭 |

**示例：**

```bash
stock-ai watch                                     # 看盘自选股，30秒刷新
stock-ai watch -c sh600519,sz000985 -i 15          # 指定股票，15秒刷新
stock-ai watch --alert-only                        # 仅监控预警（不显示行情）
```

看盘模式会持续运行，按 `Ctrl+C` 退出。每轮刷新会显示：
- 📊 实时行情表（现价、涨跌幅、成交量等）
- 📊 变动追踪表（第2轮起，对比上一轮的差异）
- ⚡ 异动捕捉提醒（价格快速变动或放量时自动提醒）
- 🚨 预警触发提醒（如果有预警被触发）

#### 变动追踪

从第 2 轮刷新起，系统会自动显示**变动追踪表**，包含：

| 列 | 说明 |
|---|---|
| **价格变动** | 与上一轮的价格差（带↑/↓箭头） |
| **涨跌幅Δ** | 涨跌幅百分比的变化量 |
| **成交量增量** | 本轮新增的成交量 |
| **累计变动** | 相对首轮监控开始时的总变动幅度 |
| **动向** | 📈上行 / 📉下行 / 横盘 + 速度标签（⚡快速 / 🔥活跃） |

#### 异动捕捉

当检测到以下情况时，系统会弹出 **⚡ 异动捕捉** 面板：

- 🚀 **快速拉升** — 单轮价格上涨 ≥ 0.5%
- 💥 **快速下跌** — 单轮价格下跌 ≥ 0.5%
- 📦 **放量** — 成交量增量超过上轮总量的 20%

> 💡 建议：使用较短的刷新间隔（如 `-i 15`）可以更灵敏地捕捉异动。

---

## 数据说明

### 数据存储

| 内容 | 位置 |
|------|------|
| 数据库 | `data/stock_trader.db`（SQLite） |
| 导出文件 | `data/exports/` |
| 图表文件 | `data/charts/` |
| 缓存 | `data/cache/` |
| 配置文件 | `config.yaml` |

### 行情数据来源

实时行情通过 `stock-data` CLI 工具获取，支持 A股、港股、美股数据。

### 交易记录说明

- 交易记录为**手动录入**，不自动连接券商
- 手续费默认按万2.5计算，卖出印花税按千1计算
- 可通过 CSV 批量导入历史交易记录

---

## 常见问题

### Q: 如何批量导入历史交易？

准备一个 CSV 文件，包含以下列：

```
stock_code,stock_name,action,price,quantity,trade_time,reason
sh600519,贵州茅台,buy,1400.00,100,2026-01-15 10:30:00,底部买入
sh600519,贵州茅台,sell,1520.00,100,2026-02-20 14:00:00,止盈
```

然后导入：

```bash
stock-ai trade import ./my_trades.csv
```

### Q: 持仓数据不对怎么办？

```bash
stock-ai rebuild
```

会根据所有交易记录重新计算持仓。

### Q: 同时查多只股票的行情？

用逗号分隔代码：

```bash
stock-ai quote sh600519,sz000858,hk00700
```

### Q: 怎么看某段时间的交易统计？

```bash
stock-ai summary --start 2026-01-01 --end 2026-03-31
```

### Q: 配置文件在哪里修改？

项目根目录的 `config.yaml`，可调整数据库路径、手续费率、图表样式等。
