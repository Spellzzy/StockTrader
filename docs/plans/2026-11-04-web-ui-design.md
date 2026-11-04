# 本地 Web UI 设计（2026-11-04）

## 目标

给 `stock-trader-ai` 包一层面向普通用户的可视化界面：双击脚本 → 自动打开浏览器
→ 看到总览、行情、报告。命令行与 TUI 继续可用，Web 是第三个入口，不重写业务逻辑。

已确认的两个决策：

- 形态：**本地 Web UI**（不是桌面 exe，不是增强 TUI）
- 启动：**双击脚本**（`启动.bat` / `start.command`），机器需已装 `requirements.txt` 依赖

## 架构

```
启动.bat / start.command
  └─ python -m app.cli web → uvicorn 127.0.0.1:8765 → 自动开浏览器

浏览器（内置静态单页：HTML + 原生 JS + 自绘 SVG，无 npm / 无 CDN）
  └─ /api/* 纯 JSON
app/web/api.py（FastAPI 路由）
  └─ app/container.py → 现有 services / ai / domain / data / visualization
```

新增目录只有 `app/web/` 与根目录两个启动脚本。CLI / TUI / 日报 / 计划任务不变。

## 数据契约

- `DataFrame → to_dict(orient="records")`，日期转 ISO 字符串
- ORM 对象用显式 DTO 转换，不直接序列化 SQLAlchemy 实例
- 所有接口返回 `{ok: true, data: ...}`；异常统一 `{ok: false, error: "..."}`，不回传堆栈
- 同步 service（sqlite + 行情子进程）统一用 `run_in_threadpool` 包裹
- 任一块数据失败只影响该块，总览页其它卡片仍渲染

## 安全约束

- 只绑 `127.0.0.1`，无账号体系（本机单用户）
- 配置页（P2）对 token / api_key 脱敏；P0 不暴露任何配置
- 写操作（P2）必须 `confirm=true` 且幂等
- 冻结的订单执行层不暴露给 Web
- 报告文件按白名单文件名读取，禁止路径穿越

## 页面与 API

第一期 8 个只读页，P0 先落 3 个（标记 ★）：

| 页面 | API | 复用方法 |
|---|---|---|
| ★ 总览 | `GET /api/overview` | `get_total_summary` / `analysis.summary` / 预警与模型状态 |
| ★ 行情 | `GET /api/quote` `GET /api/kline` `GET /api/search` | `MarketService` |
| ★ 报告 | `GET /api/reports` `GET /reports/{name}` | 直接打开 `data/reports/*.html` |
| 统计 | `GET /api/analysis/*` | `summary` / `monthly_summary` / `stock_pnl_ranking` / `max_drawdown` |
| 回测 | `POST /api/backtest/*` | `BacktestService.run` / `run_portfolio` / `rank_results` |
| 策略实验室 | `GET /api/lab/signals` `POST /api/lab/optimize` | `StrategyLab` |
| AI 预测 | `GET /api/predict` | `PredictorService.predict`（含质量闸门标记） |
| 交易/持仓 | `GET /api/trades` `/api/portfolio` | `get_trades_df` / `get_portfolio_with_market_data` |

P2 写操作：交易录入、预警、模拟盘、设置（脱敏）。

## 启动

`启动.bat` 切到项目目录、`chcp 65001`、调 `python -m app.cli web`；Mac 用 `start.command`。
命令支持 `--port` / `--no-browser` / `--host`，默认 8765 + 自动开浏览器。
新增依赖：`fastapi`、`uvicorn`（写入 `requirements.txt` 与 `setup.py`）。

## 验收标准

1. 双击 `启动.bat` → 浏览器自动打开总览页，无报错
2. 所有 API 用 `TestClient` + mock 行情单测，**零网络、零真实数据写入**
3. 每个页面调用现有 service，与 CLI 同源
4. 断网（行情失败）时前端仍渲染，只显示明确错误提示
5. `pytest` 全绿、`ruff` 0 error

## 分期

- **P0**：Web 骨架 + 启动脚本 + 总览 / 行情 / 报告 + API 单测
- **P1**：统计 / 回测 / 策略实验室 / AI 预测 / 交易持仓只读页
- **P2**：写操作（二次确认 + 幂等）
- **P3**（可选）：pywebview 桌面壳、定时刷新、异步长任务进度

## 已知风险

- 少数 CLI 命令直接 `console.print` 没有结构化返回，但服务层大多已返回 dict/DataFrame，
  需要补的只是少量 DTO 转换
- 慢操作（回测 / 优化 / 全A扫描）先同步 + 超时提示，异步进度放 P1
- 图表统一由后端 matplotlib 生成 PNG → data URL，避开前端中文字体问题
- 前端资源全部内置，不依赖 CDN，断网也能打开页面

## 明确不做

- 不做多用户 / 远程访问 / 账号体系
- 不打包 exe（保留以后用 pywebview 套壳的可能）
- 不在 Web 暴露订单执行层（当前冻结）
