# 架构整改路线（P0 ~ P3）

每个阶段单独提交，可单独回滚。完成状态以「验收证据」为准，不以主观判断为准。

---

## P0 可验证基础 ✅

目标：先建立能自动跑的验证手段，再动业务逻辑。

| 项目 | 状态 | 验收证据 |
|------|------|----------|
| pytest / ruff / coverage / pre-commit / GitHub Actions | ✅ | `pytest` 174 passed；`ruff check` 0 error |
| 补齐安装依赖（httpx / textual / click） | ✅ | `setup.py` 新增，另加 `dev` / `dl` extras |
| 修复 theme 颜色函数未导入（cli / backtest / shortcuts / tui 两处） | ✅ | 原会在相应命令路径抛 `NameError`，ruff F821 已清零 |
| 清理 47 处未使用导入与变量 | ✅ | ruff F401/F841 清零 |
| 配置默认值深拷贝 + `STOCK_AI_*` 环境变量覆盖 | ✅ | `tests/test_config.py` |
| 统一费率 `domain/fees.py` FeeModel | ✅ | `tests/test_fees.py`、`tests/test_trade_service.py` |
| 代码规范化 + 指数识别 + 模型清理脚本 | ✅ | `scripts/clean_models.py` 已清理 2 个重复 + 2 个指数模型 |

## P1 结果可信 ✅

目标：修掉会让回测收益和模型准确率失真的缺陷。

| 项目 | 状态 | 验收证据 |
|------|------|----------|
| 回测改为次日开盘成交（消除前视偏差） | ✅ | `tests/test_backtest.py`；`--fill close` 保留旧口径对照 |
| T+1 / 一字涨停不可买 / 一字跌停不可卖 / 滑点 | ✅ | 同上（含涨停跌停样本 CSV） |
| 止损止盈改用当日最高最低价 | ✅ | `test_stop_loss_uses_intraday_low_and_respects_t_plus_1` |
| ML/DL 切分留间隔、标准化只在训练集拟合 | ✅ | `app/ai/split.py` + `tests/test_ml_split.py`、`tests/test_dl_scaler.py` |
| walk-forward 滚动验证 | ✅ | `train-ai --walk-forward N` |
| 模型不再隐式训练 | ✅ | `test_predict_does_not_train_silently`；修复 Typer Option 默认值使其真正生效 |
| 落盘模型在全量数据上重训 | ✅ | 留出集只用来报准确率，模型本身重训到最新一根 K 线（`test_ml_final_fit.py`） |
| 预警冷却，不再每轮重复推送 | ✅ | `tests/test_alert_cooldown.py`；`alerts.cooldown_minutes` 默认 30 分钟 |

真实行情 A/B 对照（180 天，同一批股票与策略）：

| 标的 / 策略 | 旧口径 close | 新口径 next_open |
|---|---|---|
| sh600519 / macd_cross | -3.35% | -2.66% |
| sh600519 / rsi | -10.32% | -12.57% |
| sz002555 / macd_cross | -25.17% | -21.21% |
| sz002074 / rsi | -31.17% | -32.15% |

结论：旧口径的偏差方向不固定（有高有低），但量级可到数个百分点，之前不能作为决策依据。

## P2 架构整理 ✅

| 项目 | 状态 | 说明 |
|------|------|------|
| 领域层 `app/domain/` | ✅ | indicators（FeatureEngine 下沉）、fees、calendar；`test_domain_layer` 校验不反向依赖上层 |
| 消除 services ↔ ai 双向依赖 | ✅ | 服务层与 AI 层都只依赖 domain |
| 去掉 cli.py 自引用，改显式命令注册表 | ✅ | `tests/test_command_registry.py` 自动校验不漏注册 |
| CLI / TUI 共用服务容器 | ✅ | `app/container.py`（原 tui/services.py 提升） |
| K 线缓存 | ✅ | `app/data/market_cache.py`，`config.cache` 段真正生效 |
| `session_scope` 上下文管理器 | ✅ | 自动提交/回滚/关闭 |
| Alembic 迁移基线 | ✅ | 已在临时库验证建表；已有库需 `alembic stamp head` |
| 统一日志 + 密钥脱敏 | ✅ | `app/logging_setup.py`，日志写 `logs/stock-ai.log` |

## P3 能力扩展（部分完成）

| 项目 | 状态 | 说明 |
|------|------|------|
| 交易日历 | ✅ | `domain/calendar.py`（周末 + `market.holidays`），定时脚本已接入 |
| 模拟盘 | ✅ | `app/services/paper_broker.py` + `stock-ai paper buy/sell/show/orders/reset` |
| 交易成交推送 `on_trade` | ✅ | `NotificationManager.notify_trade`，`config.notification.on_trade` 开启后生效 |
| Transformer 接入命令行 | ✅ | `train-ai --dl --arch transformer / both` |
| 多标的组合回测 | ✅ | `BacktestService.run_portfolio` + `stock-ai bt-pf <codes>`（等权分配，合并权益曲线） |
| 选股结果直接送回测 | ✅ | `stock-ai sn --backtest`（对买入命中做组合回测） |
| 参数寻优（网格搜索） | ⬜ 未做 | 下一步 |
| 执行层 / 订单编排（阶段 0+1） | ✅ | `stock-ai order *`：Manual 人工确认通道，默认只出草稿，绝不自动真实下单 |
| QMT / Ptrade 真实通道（阶段 3） | ⬜ 未做 | 需券商量化权限与测试环境，未经验证不接 |

### 执行层（半自动）已落地内容

| 能力 | 说明 |
|------|------|
| 领域层 `domain/order.py` | 订单状态机（含 UNKNOWN 禁止重下）、幂等键、风控限额（纯函数） |
| `services/broker/` | Broker ABC + ManualBroker（草稿 CSV/MD）、MockBroker（影子）、PaperBrokerAdapter |
| `services/order_service.py` | 风控闸门、幂等创建、超时过期、重启恢复、成交回填、对账、事件审计 |
| `services/order_planner.py` | 信号 → 订单，去重、整手；支持离线信号 CSV 与自选股策略信号 |
| 2 张表 + 迁移 | `orders` / `order_events`，迁移 `da6fec2a5bda` |
| 安全默认 | `broker.enabled=false` kill switch；`--live` 必须 `--yes`；不存券商密码 |

验收：25 个执行层单测（状态机、每条风控、幂等、UNKNOWN 不重下、影子链路、
历史 K 线纸面回放、对账），全量 224 passed；离线 `order plan --no-save` 已跑通。

**明确未做**：没有连接任何券商、没有真实下单能力、没有无人值守自动交易。
`--live` 在 `broker.enabled=false` 时一律被拒绝，Manual 通道的"提交"仅生成草稿。

---

## 遗留与已知风险

1. **`config.yaml` 里有明文 PushPlus token**（文件已被 gitignore）。建议改用环境变量
   `STOCK_AI_NOTIFICATION__PUSHPLUS__TOKEN`，迁移后再把 yaml 里的值清空。
2. **交易日历的节假日需要人工维护**：`config.yaml` 的 `market.holidays`，
   每年初按交易所公告填一次，否则只会按周末判断。
3. **测试覆盖率约 24%**：`smart_digest`、`pool_loader`、`watch`、TUI、可视化仍是空白，
   后续改这些模块前应先补特征测试。
4. **`data/models/ml/` 下有 6 个我在冒烟测试期间误训练的模型**
   （sz300999 / sz000651 / sz000625 的 rf、xgb，文件名日期为 20261030），
   可直接删除：`remove-item data/models/ml/*20261030*.joblib`。
5. **Alembic 迁移与 `init_db()` 并存**：日常 CLI 仍走 `init_db()`；改模型后需
   `alembic revision --autogenerate` 生成迁移，否则迁移会落后于 ORM 定义。
6. CLI 命令层仍无任何测试，改动 `commands/*.py` 后需要手动冒烟（本次即通过
   `python -m app.cli <cmd>` 逐个验证）。
