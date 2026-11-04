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
  - [智能日报](#智能日报)
- [回测引擎](#回测引擎)
- [消息推送](#消息推送)
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
搜索/看行情 → 加自选 → 回测验证 → 设预警 → 看盘监控/智能日报 → 买入 → 看持仓 → 卖出 → 复盘分析
     ↑                                                                              |
     └──────────────────────────────────────────────────────────────────────────────┘
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
| **📰 智能日报** | | | |
| 生成日报 | `stock-ai digest` | `dg` | `stock-ai dg` |
| 生成+推送 | `stock-ai digest-push` | `dg-p` | `stock-ai dg-p` |
| 快速预览 | `stock-ai digest-preview` | `dg-v` | `stock-ai dg-v` |
| **📈 回测引擎** | | | |
| 运行回测 | `stock-ai bt <代码>` | — | `stock-ai bt sh600519 -s rsi -d 365` |
| 查看策略 | `stock-ai bt-list` | — | `stock-ai bt-list` |
| 多策略对比 | `stock-ai bt-compare <代码>` | — | `stock-ai bt-compare sh600519` |
| **📬 消息推送** | | | |
| 查看渠道 | `stock-ai notify-list` | `nl` | `stock-ai nl` |
| 测试推送 | `stock-ai notify-test` | `nt` | `stock-ai nt -c dingtalk` |
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
stock-ai dg                       # 智能日报 (digest)
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

### 智能日报

```
stock-ai dg                              # 生成日报 (digest)
stock-ai dg --llm                        # 日报 + LLM 深度分析
stock-ai dg --push                       # 生成并推送
stock-ai dg --llm --push --auto-alert    # 全套：AI+LLM+推送+自动预警
stock-ai dg-p                            # 生成并推送 (digest-push)
stock-ai dg-v                            # 快速预览 (digest-preview)
```

### 回测引擎

```
stock-ai bt sh600519                     # 回测 (默认MACD策略)
stock-ai bt sh600519 -s rsi -d 365      # RSI策略回测365天
stock-ai bt sh600519 --sl 0.05 -g       # 带止损+出图
stock-ai bt-list                         # 查看可用策略
stock-ai bt-compare sh600519             # 多策略对比
```

### 消息推送

```
stock-ai nl                              # 查看渠道配置 (notify-list)
stock-ai nt                              # 测试推送 (notify-test)
stock-ai nt -c dingtalk                  # 仅测试钉钉渠道
stock-ai nt -c email                     # 仅测试邮件渠道
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
| `dg` | digest | **d**i**g**est 日报 |
| `dg-p` | digest-push | **d**i**g**est-**p**ush 推送日报 |
| `dg-v` | digest-preview | **d**i**g**est pre**v**iew 预览 |
| `bt` | backtest run | **b**ack**t**est 回测 |
| `bt-list` | backtest list | 查看回测策略 |
| `bt-compare` | backtest compare | 多策略对比 |
| `nt` | notify-test | **n**otify-**t**est 测试推送 |
| `nl` | notify-list | **n**otify-**l**ist 渠道配置 |

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

> 手续费和印花税会**自动计算**（手续费万3、单笔最低 5 元，卖出印花税千1）。
> 费率可在 `config.yaml` 的 `fees` 段修改，交易录入与回测共用同一套口径。

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
| `--llm` | 追加 LLM 分析点评 | 关闭 |
| `--auto-train` | 缺少模型时先自动训练 | 关闭 |

输出内容：
- **综合信号**：看涨/看跌/震荡 + 星级评分
- **多模型对比**：XGBoost、RandomForest（可选 LSTM）的独立预测
- **关键因子**：MACD 金叉/死叉、RSI 超买超卖、均线排列等
- **特征重要性排名**：模型认为最重要的技术指标
- **技术指标快照**：当前各项技术指标数值

> ⚠️ 预测**不会**隐式训练模型。没有模型时会直接提示，请先 `stock-ai train-ai <代码>`，
> 或在 `predict` 上加 `--auto-train`。批量扫描时隐式训练会让耗时从秒级变成分钟级。

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
| `--walk-forward N` / `-wf N` | 只做 N 折滚动窗口验证（不保存模型） |

模型的**准确率来自时序切分后的留出集**：切分点两侧各留 horizon 天间隔，
避免「未来 N 天收益」标签把测试集信息泄漏进训练集。

```bash
stock-ai train-ai sh600519 -wf 3     # 3 折滚动验证，比单次切分更接近真实表现
```

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
| `-s / --sort` | 排序字段：chg/amp/vol/vr/tr | chg |
| `--alert-only` | 仅监控预警，不显示行情表 | 关闭 |

**示例：**

```bash
stock-ai watch                                     # 看盘自选股，30秒刷新
stock-ai watch -c sh600519,sz000985 -i 15          # 指定股票，15秒刷新
stock-ai watch --alert-only                        # 仅监控预警（不显示行情）
stock-ai watch -s vol                              # 按成交额排序
```

看盘模式会持续运行，**收盘（15:00）后自动结束**，也可手动按 `Ctrl+C` 退出。每轮刷新会显示：
- 📊 大盘指数面板（上证/深证/创业板/科创50 + 两市成交额）
- 📊 实时行情表（现价、涨跌幅、成交量、振幅、量比、委比、内外盘、距涨停/跌停等）
- 📊 变动追踪表（第2轮起，对比上一轮的差异）
- ⚡ 异动捕捉提醒（价格快速变动、放量、振幅骤增、换手飙升、逼近涨跌停）
- 🚨 预警触发提醒（如果有预警被触发）
- ⏰ 距收盘倒计时

> 💡 开盘前启动看盘会自动等待，不需要手动掐时间。

#### 变动追踪

从第 2 轮刷新起，系统会自动显示**变动追踪表**，包含：

| 列 | 说明 |
|---|---|
| **价格变动** | 与上一轮的价格差（带↑/↓箭头） |
| **涨跌幅Δ** | 涨跌幅百分比的变化量 |
| **振幅Δ** | 振幅百分比的变化量 |
| **成交量增量** | 本轮新增的成交量 |
| **量比变动** | 成交量较上轮的百分比变动 |
| **换手率Δ** | 换手率的变化量 |
| **累计变动** | 相对首轮监控开始时的总变动幅度 |
| **动向** | 📈上行 / 📉下行 / 横盘 + 速度标签（⚡快速 / 🔥活跃） |

#### 异动捕捉

当检测到以下情况时，系统会弹出 **⚡ 异动捕捉** 面板：

- 🚀 **快速拉升** — 单轮价格上涨 ≥ 0.5%
- 💥 **快速下跌** — 单轮价格下跌 ≥ 0.5%
- 📦 **放量** — 成交量增量超过上轮总量的 20%
- 🌊 **振幅骤增** — 振幅单轮扩大 ≥ 0.5%
- 🔄 **换手飙升** — 换手率单轮增加 ≥ 0.3%
- 🔺 **逼近涨停** — 距涨停价 < 1%
- 🔻 **逼近跌停** — 距跌停价 < 1%

> 💡 建议：使用较短的刷新间隔（如 `-i 15`）可以更灵敏地捕捉异动。

---

### 智能日报

智能日报（AI 盯盘助手）会批量扫描自选股，通过 AI 模型分析每只股票的走势，自动分类为看涨/震荡/看跌，并生成人话摘要。支持可选的 LLM 深度分析和自动推送。

#### 核心能力

- 🤖 **批量 AI 扫描** — 一键扫描所有自选股，输出综合信号
- 📊 **自动分类** — 看涨/震荡/看跌三档分类 + 星级评分排序
- 🧠 **LLM 深度分析** — 可选追加大模型分析，生成投资建议
- 📱 **一键推送** — 生成后自动推送到已配置的通知渠道
- 🔔 **自动预警** — 可为高风险股票自动配置预警规则

#### 三个子命令

| 命令 | 缩写 | 说明 |
|------|------|------|
| `stock-ai digest` | `dg` | 生成完整日报（AI 扫描 + 分类 + 人话摘要） |
| `stock-ai digest-push` | `dg-p` | 生成日报并推送到手机 |
| `stock-ai digest-preview` | `dg-v` | 快速预览（仅扫描，不 LLM 不推送） |

#### 命令选项

```bash
stock-ai digest [选项]
```

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `--dl` | 使用深度学习模型 (LSTM) | 关闭 |
| `--llm` | 追加 LLM 深度分析 | 关闭 |
| `--push / -p` | 生成后推送到通知渠道 | 关闭 |
| `--auto-alert` | 自动为高风险股票配置预警 | 关闭 |

#### 使用示例

```bash
# 快速预览（只扫描，不 LLM 不推送）
stock-ai digest-preview        # 缩写: dg-v

# 完整日报（AI 扫描 + 分类 + 人话摘要）
stock-ai digest                # 缩写: dg

# 完整日报 + LLM 深度分析
stock-ai digest --llm

# 生成并推送到手机（需先配置通知渠道）
stock-ai digest --push         # 或 stock-ai digest-push (dg-p)

# 一键全套：AI + LLM + 推送 + 自动预警
stock-ai digest --llm --push --auto-alert
```

#### 日报内容

日报会输出以下内容：

- 📈 **看涨组** — 评分最高的 N 只股票，附信号分析
- 📉 **看跌组** — 评分最低的 N 只股票，附风险提示
- 📊 **震荡组** — 其余股票的简要状态
- 🧠 **LLM 分析**（可选）— 大模型对整体持仓的综合分析和操作建议
- 🔔 **自动预警**（可选）— 为看跌/高风险股票自动设置预警规则

#### 定时执行

可通过系统计划任务实现每日自动执行：

**Windows 计划任务：**

```bash
# 上午开盘后执行
schtasks /create /tn "StockAI_AM" /tr "python scripts/scheduled_digest.py" /sc daily /st 10:00

# 下午收盘前执行
schtasks /create /tn "StockAI_PM" /tr "python scripts/scheduled_digest.py" /sc daily /st 14:30
```

**Linux crontab：**

```bash
# 每个交易日上午 10:00 和下午 14:30 执行
0 10 * * 1-5 cd /path/to/stock-trader-ai && python scripts/scheduled_digest.py
30 14 * * 1-5 cd /path/to/stock-trader-ai && python scripts/scheduled_digest.py
```

> 定时脚本会自动判断交易日，非交易日不会执行。

#### 工作原理

```
自选股列表
  ↓
批量获取行情 + AI 模型预测（XGBoost / RandomForest / 可选 LSTM）
  ↓
按综合评分排序 → 分类（看涨 / 震荡 / 看跌）
  ↓
组装 Markdown + Rich 终端 双格式人话摘要
  ↓
可选: LLM 深度分析（整体持仓点评 + 操作建议）
  ↓
可选: 推送到通知渠道（微信/钉钉/飞书/Telegram/邮件...）
  ↓
可选: 为高风险股票自动配置预警规则
```

---

### 回测引擎

回测引擎可以对历史行情数据运行交易策略模拟，帮你在不花真金白银的情况下验证策略效果。

#### 核心能力

- 🎯 **7 个内置策略** — MACD、均线、RSI、布林带、KDJ、双重 MACD、海龟突破
- 📊 **完整绩效报告** — 收益率、夏普比率、最大回撤、胜率、盈亏比等 30+ 指标
- 📈 **可视化图表** — 权益曲线 + 回撤图 + 买卖标记 + 交易明细图
- 🔄 **多策略对比** — 一键对比 7 个策略，按收益排名
- ⚙️ **灵活风控** — 止损、止盈、仓位比例可自定义

#### 查看可用策略

```bash
stock-ai bt-list
```

| 策略名 | 说明 |
|--------|------|
| `macd_cross` | MACD 金叉买入 / 死叉卖出（默认策略） |
| `ma_cross` | 均线交叉 (MA5 上穿 MA20 买入 / 下穿卖出) |
| `rsi` | RSI 超卖 (< 30) 买入 / 超买 (> 70) 卖出 |
| `boll` | 布林带下轨买入 / 上轨卖出 |
| `kdj` | KDJ 低位金叉买入 / 高位死叉卖出 |
| `dual_macd` | 均线 + MACD 双重确认 (更保守) |
| `turtle` | 海龟突破策略 (20日高点突破买入 / 10日低点跌破卖出) |

#### 运行单个回测

```bash
stock-ai bt <股票代码> [选项]
```

| 选项 | 缩写 | 说明 | 默认值 |
|------|------|------|--------|
| `--strategy` | `-s` | 策略名称 | `macd_cross` |
| `--days` | `-d` | 回测天数 | `180` |
| `--capital` | `-k` | 初始资金 (元) | `100000` |
| `--stop-loss` | `--sl` | 止损比例 (0.05 = 5%) | `0` (不止损) |
| `--take-profit` | `--tp` | 止盈比例 (0.1 = 10%) | `0` (不止盈) |
| `--position` | — | 仓位比例 (0~1) | `1.0` |
| `--chart` | `-g` | 生成图表 | 关闭 |

**示例：**

```bash
# 最简用法 — 默认 MACD 策略，180天，10万资金
stock-ai bt sh600519

# 指定策略和天数
stock-ai bt sh600519 -s rsi -d 365

# 带止损止盈
stock-ai bt sh600519 -s turtle --sl 0.05 --tp 0.1

# 自定义资金 + 仓位比例 (80% 仓位)
stock-ai bt sh600519 -s ma_cross -k 200000 --position 0.8

# 加 -g 生成图表（权益曲线 + 回撤 + 交易明细图）
stock-ai bt sh600519 -s macd_cross -d 365 -g
```

#### 回测报告说明

运行回测后会输出完整的绩效报告，包含以下几个板块：

| 板块 | 指标 |
|------|------|
| 📋 **基本信息** | 策略名称、回测区间、初始资金、终值、净利润 |
| 📊 **收益指标** | 总收益率、年化收益率、基准收益(买入持有)、超额收益 |
| 📉 **风险指标** | 最大回撤（金额+比例）、夏普比率、卡玛比率 |
| 🎯 **交易统计** | 总交易笔数、胜率、盈亏比、平均盈利/亏损、最大单笔盈/亏、平均持仓天数 |
| 💰 **费用统计** | 手续费、印花税合计 |
| ⭐ **综合评级** | 1~5 星评级 (基于夏普比率+收益) |

如果交易笔数 ≤ 30，还会自动输出**交易明细表**（买入/卖出日期、价格、数量、盈亏、退出原因）。

#### 多策略对比

一键对比所有策略在同一支股票上的表现：

```bash
# 7 个策略全量对比
stock-ai bt-compare sh600519

# 指定天数和资金
stock-ai bt-compare sh600519 -d 365 -k 200000

# 只对比部分策略
stock-ai bt-compare sh600519 -s "macd_cross,rsi,turtle"
```

对比结果会输出排名表，包含：总收益、年化收益、超额收益、最大回撤、夏普比率、胜率、盈亏比、交易次数、综合评分，并推荐最优策略。

#### 回测图表

使用 `-g` 参数会生成两张图表：

1. **权益曲线图** — 三合一子图：
   - 上图：策略权益曲线 vs 基准 (买入持有) + 买卖标记 (▲买入 / ▼卖出)
   - 中图：回撤曲线（标注最大回撤点）
   - 下图：持仓市值变化

2. **交易明细图** — 两合一子图：
   - 上图：每笔交易盈亏柱状图 (绿色盈利 / 红色亏损) + 退出原因标注
   - 下图：累计盈亏曲线

图表自动保存到 `data/charts/` 目录。

#### 回测配置

默认参数可在 `config.yaml` 的 `backtest` 段中修改：

#### 成交规则（重要）

回测默认按 **`fill_mode: "next_open"`** 撮合，即「今天出信号、明天开盘成交」：

- 第 N 根 K 线出现的信号，在第 N+1 根以**开盘价**成交，不使用信号当根收盘价（避免前视偏差）
- **T+1**：买入当天不能卖出
- **一字涨停无法买入**、**一字跌停无法卖出**（开=高=低=收 且方向相符）
- 止损/止盈按当日**最低价/最高价**判断，成交价取止损价与开盘价中更差的一个
- `slippage` 可设滑点：买入价上浮、卖出价下浮

如需对照改造前的口径，用 `--fill close`（信号当日收盘价成交，结果偏乐观，不建议作为决策依据）：

```bash
stock-ai bt sh600519 -s macd_cross --fill close   # 旧口径（含前视偏差）
stock-ai bt sh600519 -s macd_cross                # 默认：次日开盘成交
stock-ai bt sh600519 -s macd_cross --slippage 0.001
```

```yaml
fees:
  commission_rate: 0.0003    # 手续费率 (万三)
  min_commission: 5.0        # 单笔最低手续费 (元)
  stamp_tax_rate: 0.001      # 印花税率 (千一，A股卖出收取)

backtest:
  fill_mode: "next_open"     # 成交方式: next_open / close
  slippage: 0.0              # 滑点比例
  initial_capital: 100000    # 默认初始资金 (元)
  # commission_rate / tax_rate 不填则沿用上面的 fees 段
  stop_loss: 0.0             # 默认止损比例 (0=不止损)
  take_profit: 0.0           # 默认止盈比例 (0=不止盈)
  position_size: 1.0         # 单次建仓资金比例 (0~1)
  default_days: 180          # 默认回测天数
  default_strategy: "macd_cross"  # 默认策略
```

#### 推荐使用流程

```bash
# 第一步：查看有哪些策略
stock-ai bt-list

# 第二步：全量对比，找出最适合的策略
stock-ai bt-compare sh600519 -d 365

# 第三步：对最优策略深入回测，加上风控和图表
stock-ai bt sh600519 -s macd_cross -d 365 --sl 0.05 -g

# 第四步：换一只股票验证策略的普适性
stock-ai bt sz000858 -s macd_cross -d 365 --sl 0.05 -g
```

#### 回测原理简述

```
获取K线数据 (最近N天日K)
  ↓
特征工程 (40+技术指标: MA/EMA/MACD/RSI/KDJ/BOLL/ATR/OBV 等)
  ↓
策略信号生成 (每根K线产生 买入/卖出/持有 信号)
  ↓
模拟交易 (按信号买卖，考虑手续费/印花税/整手限制)
  ├─ 止损/止盈检查
  ├─ 每日跟踪权益曲线
  └─ 到期自动平仓
  ↓
绩效计算 (收益率/夏普/回撤/胜率 等30+指标)
  ↓
输出报告 + 可选图表
```

> ⚠️ **风险提示**：回测结果基于历史数据，不代表未来收益。请注意过拟合风险，建议在多只股票、多个时间段交叉验证。

---

### 回测缩写速查

```
stock-ai bt sh600519                     # 回测 (默认MACD策略)
stock-ai bt sh600519 -s rsi -d 365      # RSI策略回测365天
stock-ai bt sh600519 --sl 0.05 -g       # 带止损+出图
stock-ai bt-list                         # 查看可用策略
stock-ai bt-compare sh600519             # 多策略对比
stock-ai bt-compare sh600519 -s "rsi,turtle,macd_cross"  # 指定策略对比
```

---

## 选股引擎（Screener）

通过自定义条件组合，从市场中筛选符合要求的股票。条件可在 `config.yaml` 的 `screener` 段灵活配置，无需改代码。

### 命令速查

```bash
# 同时扫描买入+卖出信号（默认）
stock-ai screen                       # 缩写: sn

# 仅买入扫描
stock-ai sn --side buy

# 仅卖出扫描（基于当前持仓）
stock-ai sn --side sell

# 临时切换股票池
stock-ai sn --pool watchlist          # 自选股
stock-ai sn --pool portfolio          # 当前持仓
stock-ai sn --pool all_a              # 全A股 (~5000只)
stock-ai sn --pool "sh600519,sz000858"   # 直接指定代码
stock-ai sn --pool "file:./codes.txt"    # 本地文件（每行一个代码）

# 临时改聚合模式
stock-ai sn --mode-buy any            # 任一条件命中即可（默认 all）
stock-ai sn --mode-buy atleast:3      # 至少 3 条满足

# 命中后推送到通知渠道
stock-ai sn --push

# 列出所有可用条件
stock-ai sn --list-conditions

# 全A代码缓存管理
stock-ai sn-pool-build                # 查看缓存信息（无缓存则首次构建）
stock-ai sn-pool-build --force        # 强制重建
```

### 扫描全A股市场

要扫描全A股市场（约 5000+ 只），第一次需要构建代码缓存：

```bash
# 第一步：构建全A代码缓存（约 1~3 分钟，仅首次）
stock-ai sn-pool-build

# 第二步：直接扫描全A
stock-ai sn --pool all_a

# 缓存默认 7 天有效，过期会自动重建；也可手动刷新
stock-ai sn --pool all_a:refresh
```

> ⏱️ **耗时参考**：5000 只股票全A扫描，并发 4 线程约 5~10 分钟（受限于行情接口带宽）。
> 想加快可以在 config.yaml 把 `max_workers` 调到 8，但请注意接口频控。
>
> ⚠️ **建议**：全A扫描比较耗时，可以用 `pool_size_limit` 控制规模做局部测试，
> 或先用 `--pool watchlist` 把规则调好再放大。

### 配置示例（config.yaml）

```yaml
screener:
  pool: "watchlist"          # 默认股票池
  min_kline: 30              # 最少 K 线数
  benchmark: "sz399101"      # 行业/大盘基准（中证1000）

  buy:
    mode: "all"              # 所有条件都满足才命中
    rules:
      - { name: ma_uptrend,    params: { ma: 20, lookback: 5 } }   # MA20 向上
      - { name: price_above_ma, params: { ma: 20 } }                # 价站上 MA20
      - { name: volume_expand, params: { ma_window: 5, ratio: 1.5 } }  # 量比 ≥1.5
      - { name: sector_strong, params: { window: 5 } }              # 5日跑赢基准

  sell:
    mode: "any"              # 任一条件触发即卖
    rules:
      - { name: price_below_ma, params: { ma: 10 } }                # 跌破 MA10
      - { name: bearish_volume, params: { drop_pct: 3.0, vol_ratio: 1.5 } }  # 放量长阴
      - { name: loss_pct,       params: { threshold: 8.0 } }        # 亏损 8%
```

### 内置条件清单

| 条件名 | 用途 | 主要参数 |
|---|---|---|
| `ma_uptrend` | 均线向上 | `ma`(均线周期), `lookback`(回看天数) |
| `price_above_ma` | 价站上均线 | `ma` |
| `price_below_ma` | 价跌破均线 | `ma` |
| `volume_expand` | 成交量放大 | `ma_window`, `ratio` |
| `sector_strong` | 跑赢基准 | `window`, `advantage`(领先幅度%) |
| `ma_bull` | 多头排列 MA5>10>20 | — |
| `macd_golden` / `macd_dead` | MACD 金叉/死叉 | `lookback` |
| `rsi_below` / `rsi_above` | RSI 超卖/超买 | `period`, `threshold` |
| `breakout` | 突破 N 日新高 | `window` |
| `bearish_volume` | 放量长阴 | `drop_pct`, `vol_ratio`, `ma_window` |
| `loss_pct` / `profit_pct` | 亏损/盈利达阈值（需持仓） | `threshold`(%) |

### 聚合模式

- **`all`** — 全部条件都满足（默认买入用）
- **`any`** — 任一条件满足（默认卖出用）
- **`atleast:N`** — 至少 N 个条件满足

### 扩展自定义条件

在 `app/services/screener_service.py` 用装饰器注册即可：

```python
@register_condition("my_custom")
def my_custom(ctx: ScreenContext, params: dict) -> ConditionResult:
    # ctx.df 已含 ma5/ma10/ma20/macd/rsi 等所有指标
    # ctx.last 是最新一根 K 线
    # ctx.position 是持仓信息（卖出场景才有）
    threshold = params.get("threshold", 0)
    val = ctx.last["close"]
    return ConditionResult(val > threshold, f"价 {val:.2f}")
```

注册后立即可在 config.yaml 中引用，无需重启外部服务。

---

## 消息推送

预警触发后自动推送通知到手机/群聊/邮箱，支持 **7 种渠道** 同时推送。

### 支持的渠道

| 渠道 | 说明 | 免费额度 | 获取方式 |
|------|------|----------|----------|
| **Server酱** | 微信推送 | 5条/天 | [sct.ftqq.com](https://sct.ftqq.com) 获取 send_key |
| **PushPlus** | 微信推送 | 200条/天 | [pushplus.plus](https://www.pushplus.plus) 获取 token |
| **钉钉** | 群机器人 | 无限制 | 群设置→智能群助手→自定义机器人 |
| **飞书** | 群机器人 | 无限制 | 群设置→群机器人→自定义机器人 |
| **Telegram** | Bot 推送 | 无限制 | @BotFather 创建 Bot |
| **邮件** | SMTP 邮件 | 无限制 | 各邮箱 SMTP 授权码 |
| **企业微信** | 群机器人 | 无限制 | 群聊→添加群机器人→Webhook |

### 配置方法

编辑项目根目录 `config.yaml`，在 `notification` 段中配置：

```yaml
notification:
  enabled: true        # 全局开关
  on_alert: true       # 预警触发时推送
  on_trade: false      # 交易成交时推送 (未来扩展)

  channels:
    # 以 Server酱为例
    serverchan:
      enabled: true
      send_key: "SCT..."    # 登录 sct.ftqq.com 获取

    # 以钉钉为例
    dingtalk:
      enabled: true
      webhook: "https://oapi.dingtalk.com/robot/send?access_token=..."
      secret: "SEC..."      # 加签密钥
```

> 💡 可以同时启用多个渠道，预警触发时会**并行推送**到所有已启用的渠道。

### 推送命令

```bash
# 查看所有渠道配置状态
stock-ai notify-list                     # 缩写: nl

# 发送测试消息（验证配置是否正确）
stock-ai notify-test                     # 缩写: nt

# 仅测试某个渠道
stock-ai notify-test -c dingtalk
stock-ai notify-test -c serverchan
stock-ai notify-test -c email
```

### 推送触发流程

```
预警条件满足 → alert_service._record_trigger()
  ↓
NotificationManager.notify_alert()
  ↓
并行发送到所有已启用渠道
  ├─ Server酱 (微信)
  ├─ PushPlus (微信)
  ├─ 钉钉群机器人
  ├─ 飞书群机器人
  ├─ Telegram Bot
  ├─ 邮件 (SMTP)
  └─ 企业微信群机器人
```

### 推送内容示例

预警触发时推送的消息包含：

- 📌 **股票信息** — 代码、名称
- 💰 **当前价格** — 实时价格、涨跌幅
- ⚠️ **触发条件** — 触发的预警描述
- 🕐 **触发时间** — 精确到秒

### 缩写速查

| 缩写 | 全称 | 说明 |
|------|------|------|
| `nt` | notify-test | 发送测试通知 |
| `nl` | notify-list | 查看渠道配置 |

> ⚠️ **安全提示**：`config.yaml` 中包含各渠道的密钥/Token，请勿将配置文件提交到公开仓库。建议将 `config.yaml` 加入 `.gitignore`。

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
- 手续费默认按万3计算（单笔最低 5 元），A股卖出印花税按千1计算
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

### Q: 数据库结构变了怎么升级？

项目已接入 Alembic 迁移（开发依赖 `pip install -r requirements-dev.txt`）：

```bash
alembic upgrade head      # 升级到最新结构
alembic current           # 查看当前版本
alembic revision --autogenerate -m "说明"   # 模型改了之后生成迁移
```

**已经存在的数据库**需要先标记为最新（否则会重复建表报错）：

```bash
alembic stamp head
```

日常使用不需要手动跑迁移，CLI 启动时的 `init_db()` 仍会建表并补齐新增列。

### Q: 不想用命令行，怎么用图形界面？

**双击项目目录里的 `启动.bat`**（Mac/Linux 用 `start.command`），会自动启动本地服务并打开浏览器。
等价命令是 `stock-ai web`，可加 `--port 9000` / `--no-browser`。

```bash
pip install -r requirements.txt   # 首次使用，装好依赖
启动.bat                          # 之后每次双击即可
```

浏览器打开 `http://127.0.0.1:8765/`，按 Ctrl+C 停止服务。当前提供 12 个页面（8 个只读 + 4 个写操作/设置）：

| 页面 | 内容 |
|------|------|
| 总览 | 总盈亏 / 浮动盈亏 / 市值 / 交易笔数、当前持仓明细、预警与模型数量 |
| 行情 | 多只股票实时报价（空格或逗号分隔）、K 线收盘价折线图 |
| 统计 | 交易摘要、月度盈亏、个股排名、最大回撤 |
| 回测 | 单标的回测（结果卡 + 权益曲线 + 交易明细）、7 策略对比 |
| 策略实验室 | 7 策略信号质量、参数网格 + rolling walk-forward（样本不足会标注） |
| AI 预测 | 综合信号、模型准确率与质量闸门提示、关键因子、指标快照；代码框左侧下拉可直接选「我的自选」或「当前持仓」（选中只填代码，仍需点「开始预测」） |
| 交易持仓 | 持仓明细与最近 30 笔交易，支持行内手工校正 / 解锁 / 全量重建 |
| 报告 | `data/reports/` 下已生成的 HTML 报告，点击直接打开 |
| 录入交易 | 买/卖录入，写入 trades 表并重建持仓 |
| 预警 | 规则列表、新增、启停、删除 |
| 模拟盘 | 虚拟账户、持仓/成交、虚拟下单、重置 |
| 设置 | 只读配置查看，密钥脱敏并给出对应环境变量名 |

回测、寻优、预测这类慢操作只在点击按钮时执行，切换页面不会自动触发。
Web 侧预测固定 `auto_train=False`，不会偷偷训练模型。

**写操作安全机制**：所有写请求必须带 `confirm: true`（页面勾选「确认执行」，
预警行内操作与模拟盘重置用浏览器确认框）；每个请求带前端生成的 `client_id`
幂等键，重复提交直接返回首次结果，`web_writes` 表落库，重启后依然有效。
同一个幂等键换请求内容会被拒绝（409）。设置页只读，token / api_key 只显示
「已配置 / 未配置」，不回传明文。

### Q: 怎么手工改持仓数量 / 成本价？

在「交易持仓」页点某一行的 **编辑**，填数量、成本价、名称与校正理由，勾选确认后保存。
该行会被标为 **手工锁定**（`manual_override=true`），来源列显示「手工锁定」，
鼠标悬停可看校正留痕（时间、原值→新值、理由）。

> ⚠️ 持仓本来是从 `trades` 表派生出来的，手工校正等于引入第二套真相：
> **普通「重建持仓」会跳过被锁定的行**，校正值不会被新录入的交易覆盖。
> 校正不会改动任何交易记录，`total_cost` 会自动按 `数量 × 成本价` 重算。

要恢复派生值：点该行的 **解除锁定**，系统会立即按交易记录重算这一行。
要一次性清掉全部手工校正：点页头的 **从交易全量重建**（危险操作，需浏览器确认，
会清除所有锁定标记，不可撤销）。

数据库迁移：`portfolio` 表新增 `manual_override` / `override_note` / `override_at`
三列，迁移 `b7f2c9d1e340`；已有库启动时由 `init_db()` 幂等补列，日常无需手动跑迁移。

设计文档见 `docs/plans/2026-11-04-web-ui-design.md`。约束：只监听 `127.0.0.1`、无账号体系、
前端资源全内置（断网也能打开页面，行情失败会明确提示）、不暴露冻结的订单执行层。
命令行与 TUI 不受影响，仍可照常使用。

### Q: 怎么判断一个策略值不值得用？

```bash
stock-ai signal-report sz002555 --all   # 缩写 sr，7 个策略逐一对比
stock-ai optimize sz002555 -s ma_cross  # 缩写 opt，参数网格 + 滚动窗口
```

`signal-report` 输出：信号数、未来 N 日方向命中率、样本内/样本外命中率、衰减、
配对交易胜率、平均持仓天数、买入持有基准。**命中率 50% 约等于抛硬币**；
衰减（样本内 − 样本外）过大说明参数是在历史里挑出来的。

`optimize` 先做参数网格搜索（每组跑一次完整回测，次日开盘成交口径），
再做 rolling walk-forward：每折用训练段挑参数、测试段验证。
信号样本不足的折会标「样本不足」，不会给出看似可信的衰减值。

### Q: 怎么把策略信号变成可执行的订单？

> **⏸ 该功能当前冻结，不对外开放。** 执行层代码与测试保留在仓库里，
> 但默认不会挂到 CLI（`stock-ai order` 不可见）。需要恢复时设置
> `STOCK_AI_FEATURES__ORDER_ENABLED=true` 或在 `config.yaml` 里打开
> `features.order_enabled`。当前精力放在策略有效性与使用体验上。

以下内容是解冻后的用法说明。

`stock-ai order` 是**半自动执行层**：默认只生成草稿，绝不自动真实下单。

```bash
# 离线纸面回放（不落库）
stock-ai order plan -f tests/fixtures/signals_demo.csv --no-save

# 用自选股最新策略信号编排并落库
stock-ai order plan --from-watchlist -s macd_cross

# 手工建单 / 查看 / 风控检查
stock-ai order create sh600519 buy 1400 --qty 100 -s manual
stock-ai order list
stock-ai order risk <幂等键>

# 提交（默认 dry-run，只出草稿；--live 需配置开启 + --yes）
stock-ai order submit <幂等键>

# 在券商客户端人工下单后回填成交（写 trades 表 + 推送 + 重建持仓）
stock-ai order fill <幂等键> --price 1400.00

# 运维
stock-ai order draft          # 重新导出当日草稿
stock-ai order cancel <幂等键>
stock-ai order expire         # 超时清理
stock-ai order recover        # 重启恢复（状态不明标 UNKNOWN，绝不重下）
stock-ai order reconcile      # 已成交订单 vs trades 表对账
```

配置文件 `broker:` / `risk:` 段（见 `config.yaml.example`）：

- `broker.enabled` 默认 `false`，这是 kill switch；为 false 时 `--live` 一律被拒绝
- `broker.name`：`manual`（人工确认，默认）/ `mock`（影子）/ `paper`（模拟盘）
- `risk` 段：白名单、单笔上限 5 万、单日上限 10 万、最大持仓数、单票仓位比、超时、二次确认
- 密钥不要写进配置，用环境变量，例如 `STOCK_AI_BROKER__ENABLED=true`

产物：`data/orders/orders_YYYYMMDD.csv` 和 `.md` 草稿；订单与状态变更存
`orders` / `order_events` 两张表。

> 目前**没有连接任何券商，也没有真实下单能力**。`--live` 在默认配置下被拒绝，
> Manual 通道的"提交"只是生成一份给人看的草稿。草稿与预测结果均不构成投资建议。

### Q: 每天自动生成的报告在哪？

Windows 计划任务 `StockAI_AM`（10:00）和 `StockAI_PM`（14:30）每天各跑一次，
产出都在 `data/reports/`：

| 文件 | 内容 |
|------|------|
| `digest_YYYYMMDD_am.md` / `_pm.md` | 智能日报正文（Markdown） |
| `daily_YYYYMMDD_am.html` / `_pm.html` | 可视化报告（图表内嵌，可直接打开） |
| `report_YYYYMMDD.html` | 手动执行 `stock-ai report` 生成的报告 |

日志在 `logs/digest_YYYYMMDD.log`，同时会推送到 `config.yaml` 里已启用的渠道。
周末和 `market.holidays` 里配置的节假日会自动跳过。

> 计划任务必须用**绝对路径**调用脚本，因为它默认从 `C:\Windows\System32` 启动，
> 用相对路径 `python scripts/scheduled_digest.py` 会直接报 exit code 2。

### Q: 想要一个能直接看/能分享的总览？

```bash
stock-ai report              # 生成 data/reports/report_YYYYMMDD.html
stock-ai rp                  # 缩写
stock-ai report --no-chart   # 只要表格，出得快
stock-ai report --with-bt --bt-code sz002555   # 额外附一份多策略回测对比
```

单文件 HTML，图表以 base64 内嵌，双击即可打开，也可以直接发给别人。
内容包含：账户概览（总盈亏/浮动/已实现/市值/胜率/盈亏比/最大回撤）、当前持仓、
累计收益曲线、月度盈亏、胜负统计、持仓分布、个股盈亏排名、最近 20 笔交易。

### Q: 配置文件在哪里修改？

项目根目录的 `config.yaml`，可调整数据库路径、手续费率、图表样式等。
