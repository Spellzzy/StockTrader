"""本地 Web UI — JSON API 层

只做适配，不写业务逻辑：所有数据都来自现有 services / domain / data。
同步的 sqlite + 行情子进程调用统一走 run_in_threadpool，避免阻塞事件循环。
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.config import PROJECT_ROOT, get_config

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "data" / "reports"

app = FastAPI(
    title="Stock Trader AI",
    description="本地 Web UI（只监听 127.0.0.1）",
    version=__version__,
    docs_url="/api/docs",
)


# ==================== 通用工具 ====================

def _plain(value: Any) -> Any:
    """递归转成纯 Python 类型

    pandas / SQLAlchemy 会产出 numpy.int64、Timestamp、Decimal，
    FastAPI 的 Pydantic 序列化器遇到这些会直接 500。
    """
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, np.generic):
        return _plain(value.item())
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_plain(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return [_plain(v) for v in value.tolist()]
    return str(value)


def ok(data: Any) -> dict:
    """统一成功响应，数据先归一化保证可序列化"""
    return {"ok": True, "data": _plain(data)}


def _safe(fn: Callable, default: Any = None, *args, **kwargs) -> Any:
    """单块数据失败不影响其它块"""
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        logger.warning(f"数据块生成失败，已跳过: {e}")
        return default


def df_records(df: pd.DataFrame) -> list[dict]:
    """DataFrame → JSON 安全的 records（日期转字符串、NaN 转 None）"""
    if df is None or df.empty:
        return []
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = out[col].dt.strftime("%Y-%m-%d")
    out = out.astype(object).where(pd.notnull(out), None)
    return out.to_dict(orient="records")


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """覆盖 FastAPI 默认的 {"detail": ...}，让所有错误格式一致"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"ok": False, "error": str(exc.detail)},
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """参数校验失败也用统一格式，且不回传原始请求体"""
    first = exc.errors()[0] if exc.errors() else {}
    location = ".".join(str(x) for x in first.get("loc", []))
    return JSONResponse(
        status_code=422,
        content={"ok": False, "error": f"参数不合法: {location} {first.get('msg', '')}".strip()},
    )


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    """统一错误格式，不把堆栈回传给前端"""
    logger.exception(f"API 异常 {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"ok": False, "error": "服务内部错误，详情见 logs/stock-ai.log"},
    )


# ==================== 数据块（单独函数，方便测试打桩） ====================

def _alert_count() -> int:
    from sqlalchemy import func, select

    from app.db.database import session_scope
    from app.models.alert import Alert

    with session_scope() as session:
        return int(session.execute(
            select(func.count(Alert.id)).where(Alert.is_active.is_(True))
        ).scalar_one())


def _model_count() -> int:
    save_dir = Path(get_config().get("ai", {}).get("model", {}).get("save_dir", "./data/models"))
    return len(list((save_dir / "ml").glob("*.joblib")))


def _report_files() -> list[dict]:
    if not DEFAULT_REPORT_DIR.exists():
        return []
    files = []
    for path in sorted(DEFAULT_REPORT_DIR.iterdir(), key=lambda p: p.name, reverse=True):
        if path.is_file() and path.suffix in (".html", ".md"):
            files.append({
                "name": path.name,
                "size": path.stat().st_size,
                "updated_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
                "kind": "html" if path.suffix == ".html" else "markdown",
            })
    return files


def _safe_report_path(name: str) -> Path:
    """防路径穿越：只接受纯文件名 + 白名单后缀"""
    if Path(name).name != name or name.startswith(".") or Path(name).suffix not in (".html", ".md"):
        raise HTTPException(status_code=400, detail="非法文件名")
    path = DEFAULT_REPORT_DIR / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="报告不存在")
    return path


# ==================== 路由 ====================

@app.get("/api/health")
async def health() -> dict:
    return ok({
        "version": __version__,
        "time": datetime.now().isoformat(timespec="seconds"),
        "features": {"order_enabled": get_config().get("features", {}).get("order_enabled", False)},
    })


@app.get("/api/overview")
async def overview() -> dict:
    from app.services.analysis_service import AnalysisService
    from app.services.portfolio_service import PortfolioService

    def collect() -> dict:
        portfolio = PortfolioService()
        analysis = AnalysisService()

        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "portfolio": _safe(portfolio.get_total_summary, {}),
            "analysis": _safe(analysis.summary, {}),
            "alerts_active": _safe(_alert_count, 0),
            "models": _safe(_model_count, 0),
            "reports": len(_safe(_report_files, [])),
            "warnings": [],
        }

    data = await run_in_threadpool(collect)
    if not data["portfolio"]:
        data["warnings"].append("持仓数据不可用")
    if not data["analysis"]:
        data["warnings"].append("统计摘要不可用")
    return ok(data)


@app.get("/api/quote")
async def quote(codes: str = Query(..., description="股票代码，逗号或空格分隔")) -> dict:
    from app.models.stock import parse_stock_codes
    from app.services.market_service import MarketService

    code_list = parse_stock_codes(codes)
    if not code_list:
        raise HTTPException(status_code=400, detail="未提供有效的股票代码")

    def collect() -> dict:
        data = MarketService().get_quote(*code_list)
        rows = []
        for code in code_list:
            item = (data or {}).get(code)
            if item:
                rows.append({"code": code, **item})
        return rows

    return ok({"codes": code_list, "rows": await run_in_threadpool(collect)})


@app.get("/api/kline")
async def kline(
    code: str = Query(..., description="股票代码"),
    count: int = Query(120, ge=10, le=1000),
    period: str = Query("day"),
) -> dict:
    from app.services.market_service import MarketService

    def collect():
        df = MarketService().get_kline_df(code, period=period, count=count)
        return df_records(df.tail(count))

    return ok({"code": code, "period": period, "rows": await run_in_threadpool(collect)})


@app.get("/api/search")
async def search(keyword: str = Query(..., min_length=1)) -> dict:
    from app.services.market_service import MarketService

    result = await run_in_threadpool(MarketService().search, keyword)
    return ok({"keyword": keyword, "result": result})


@app.get("/api/reports")
async def reports() -> dict:
    return ok({"files": await run_in_threadpool(_report_files)})


@app.get("/reports/{name}", response_class=HTMLResponse)
async def open_report(name: str):
    """在浏览器里打开已生成的 HTML 报告"""
    path = _safe_report_path(name)
    if path.suffix != ".html":
        raise HTTPException(status_code=400, detail="只支持打开 HTML 报告")
    return FileResponse(path, media_type="text/html")


# ==================== P1：统计 / 交易持仓 ====================

def _analysis():
    from app.services.analysis_service import AnalysisService

    return AnalysisService()


@app.get("/api/analysis/summary")
async def analysis_summary() -> dict:
    return ok(await run_in_threadpool(_analysis().summary))


@app.get("/api/analysis/monthly")
async def analysis_monthly() -> dict:
    return ok({"rows": df_records(await run_in_threadpool(_analysis().monthly_summary))})


@app.get("/api/analysis/ranking")
async def analysis_ranking() -> dict:
    return ok({"rows": df_records(await run_in_threadpool(_analysis().stock_pnl_ranking))})


@app.get("/api/analysis/drawdown")
async def analysis_drawdown() -> dict:
    return ok(await run_in_threadpool(_analysis().max_drawdown))


@app.get("/api/trades")
async def trades(limit: int = Query(50, ge=1, le=500)) -> dict:
    def collect():
        df = _analysis().get_trades_df()
        return df_records(df.tail(limit).iloc[::-1])

    return ok({"rows": await run_in_threadpool(collect)})


@app.get("/api/portfolio")
async def portfolio(include_cleared: bool = False) -> dict:
    from app.services.portfolio_service import PortfolioService

    def collect():
        service = PortfolioService()
        return {
            "holdings": service.get_portfolio_with_market_data(
                include_cleared=include_cleared
            ),
            "summary": service.get_total_summary(),
            "include_cleared": include_cleared,
        }

    return ok(await run_in_threadpool(collect))


@app.get("/api/code-picker")
async def code_picker() -> dict:
    """代码快捷选择数据源：已收藏（自选股）+ 当前持仓

    只查本地库，不请求行情，保证下拉秒开。
    """
    from app.services.portfolio_service import PortfolioService
    from app.services.watchlist_service import WatchlistService

    def collect():
        watched = [
            {"code": s.code, "name": s.name or ""}
            for s in WatchlistService().list_watched()
        ]
        holdings = [
            {"code": h.stock_code, "name": h.stock_name or ""}
            for h in PortfolioService().get_portfolio()
        ]
        return {"watchlist": watched, "holdings": holdings}

    return ok(await run_in_threadpool(collect))


@app.get("/api/watchlist/quotes")
async def watchlist_quotes() -> dict:
    """我的自选 · 实时行情（含自选备注）

    复用 WatchlistService.list_watched_with_quote()，拉不到行情时保留
    股票记录、价格字段为 0，不抛错。
    """
    from datetime import datetime as _dt

    from app.services.watchlist_service import WatchlistService

    def collect():
        return {
            "rows": WatchlistService().list_watched_with_quote(),
            "generated_at": _dt.now().isoformat(timespec="seconds"),
        }

    return ok(await run_in_threadpool(collect))


def _kline_tech(rows: list[dict]) -> dict:
    """从 K 线记录算轻量技术指标（纯 Python，不跑模型、不触网）"""
    closes = []
    for r in rows:
        try:
            if r.get("close") is not None:
                closes.append(float(r["close"]))
        except (TypeError, ValueError):
            continue
    if not closes:
        return {}

    last = closes[-1]
    ma5 = sum(closes[-5:]) / len(closes[-5:])
    ma20 = sum(closes[-20:]) / len(closes[-20:])
    chg20 = None
    if len(closes) > 20 and closes[-21]:
        chg20 = (last / closes[-21] - 1) * 100
    rets = [closes[i] / closes[i - 1] - 1
            for i in range(1, len(closes)) if closes[i - 1]]
    volatility = None
    if len(rets) >= 2:
        from statistics import pstdev
        volatility = pstdev(rets[-20:]) * 100
    high, low = max(closes), min(closes)
    return {
        "ma5": round(ma5, 3),
        "ma20": round(ma20, 3),
        "change_20d": round(chg20, 2) if chg20 is not None else None,
        "volatility_20d": round(volatility, 2) if volatility is not None else None,
        "high_60d": round(high, 3),
        "low_60d": round(low, 3),
        "range_position": round((last - low) / (high - low) * 100, 1)
        if high > low else None,
    }


@app.get("/api/stock/detail")
async def stock_detail(code: str = Query(..., min_length=4)) -> dict:
    """个股详情子页面数据：一次聚合报价 / 走势 / 指标 / 本股状态

    只读接口。行情与 K 线各自单独容错，任一拉不到也返回其余信息。
    """
    from sqlalchemy import func, select

    from app.db.database import session_scope
    from app.models.alert import Alert
    from app.models.portfolio import PortfolioRecord
    from app.models.stock import Stock, normalize_stock_code
    from app.models.trade import Trade
    from app.services.market_service import MarketService

    try:
        norm_code = normalize_stock_code(code)
    except Exception:
        raise HTTPException(status_code=400, detail="无效的股票代码")

    def collect():
        market = MarketService()
        try:
            quote = (market.get_quote(norm_code) or {}).get(norm_code, {}) or {}
        except Exception as e:
            logger.warning(f"详情行情获取失败 {norm_code}: {e}")
            quote = {}
        try:
            df = market.get_kline_df(norm_code, count=60)
            rows = df_records(df.tail(60))
        except Exception as e:
            logger.warning(f"详情K线获取失败 {norm_code}: {e}")
            rows = []

        stock_info, holding, alert_count, recent = {}, None, 0, []
        try:
            with session_scope() as s:
                stock = s.execute(
                    select(Stock).where(Stock.code == norm_code)
                ).scalar_one_or_none()
                if stock:
                    stock_info = {
                        "name": stock.name or "",
                        "market": stock.market or "",
                        "industry": stock.industry or "",
                        "sector": stock.sector or "",
                        "is_watched": bool(stock.is_watched),
                        "watch_note": stock.watch_note or "",
                    }
                h = s.execute(
                    select(PortfolioRecord).where(
                        PortfolioRecord.stock_code == norm_code
                    )
                ).scalar_one_or_none()
                if h:
                    holding = {
                        "quantity": h.quantity, "avg_cost": h.avg_cost,
                        "total_cost": h.total_cost,
                        "realized_profit": h.realized_profit,
                        "manual_override": bool(h.manual_override),
                        "is_cleared": h.quantity <= 0,
                    }
                alert_count = s.scalar(
                    select(func.count()).select_from(Alert)
                    .where(Alert.stock_code == norm_code)
                ) or 0
                trades = s.execute(
                    select(Trade).where(Trade.stock_code == norm_code)
                    .order_by(Trade.trade_time.desc()).limit(5)
                ).scalars().all()
                recent = [{
                    "trade_time": t.trade_time, "action": t.action,
                    "price": t.price, "quantity": t.quantity, "profit": t.profit,
                } for t in trades]
        except Exception as e:
            logger.warning(f"详情本地数据读取失败 {norm_code}: {e}")

        return {
            "code": norm_code,
            "name": stock_info.get("name") or quote.get("name") or "",
            "quote": quote,
            "kline": rows,
            "tech": _kline_tech(rows),
            "stock": stock_info,
            "holding": holding,
            "alert_count": alert_count,
            "recent_trades": recent,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        }

    return ok(await run_in_threadpool(collect))


@app.get("/api/stock/profile")
async def stock_profile(code: str = Query(..., min_length=4)) -> dict:
    """公司资料（按需加载，避免拖慢详情首屏）"""
    from app.models.stock import normalize_stock_code
    from app.services.market_service import MarketService

    try:
        norm_code = normalize_stock_code(code)
    except Exception:
        raise HTTPException(status_code=400, detail="无效的股票代码")

    def collect():
        try:
            data = MarketService().get_profile(norm_code)
        except Exception as e:
            logger.warning(f"公司资料获取失败 {norm_code}: {e}")
            return {"error": str(e)}
        if isinstance(data, dict):
            inner = data.get("data")
            if isinstance(inner, dict):
                return inner
            return data
        return {"raw": str(data)}

    return ok({"code": norm_code, "profile": await run_in_threadpool(collect)})


@app.post("/api/cache/clear-quotes")
async def clear_quotes_cache() -> dict:
    """清空服务端行情缓存，供手动「刷新」强制拉新行情

    只影响内存缓存，不改动任何业务数据；重复调用无副作用。
    """
    from app.data.stock_data_client import clear_quote_cache

    return ok({"cleared": clear_quote_cache()})


@app.get("/api/strategies")
async def strategies() -> dict:
    from app.services.strategy import list_strategies

    return ok({"items": await run_in_threadpool(list_strategies)})


# ==================== P1：回测 ====================

class BacktestRequest(BaseModel):
    code: str
    strategy: str = "macd_cross"
    days: int = Field(180, ge=30, le=1000)
    initial_capital: float = 100000.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    fill_mode: str = "next_open"
    slippage: float = 0.0


class CompareRequest(BaseModel):
    code: str
    days: int = Field(180, ge=30, le=1000)
    initial_capital: float = 100000.0
    strategies: list[str] = []


class PortfolioBacktestRequest(BaseModel):
    # 兼容命令行习惯：既接受 ["a","b"] 也接受 "a,b"
    codes: str | list[str]
    strategy: str = "macd_cross"
    days: int = Field(180, ge=30, le=1000)
    initial_capital: float = 100000.0


def _run_backtest(req: BacktestRequest) -> dict:
    from app.services.backtest_service import BacktestService

    result = BacktestService().run(
        code=req.code, strategy=req.strategy, days=req.days,
        initial_capital=req.initial_capital, stop_loss=req.stop_loss,
        take_profit=req.take_profit, fill_mode=req.fill_mode,
        slippage=req.slippage,
    )
    data = result.to_dict()
    data["equity_curve"] = df_records(result.equity_curve)
    return data


@app.post("/api/backtest/run")
async def backtest_run(req: BacktestRequest) -> dict:
    return ok(await run_in_threadpool(_run_backtest, req))


@app.post("/api/backtest/compare")
async def backtest_compare(req: CompareRequest) -> dict:
    from app.services.backtest_service import BacktestService
    from app.services.strategy import list_strategy_names

    def collect():
        names = req.strategies or list_strategy_names()
        service = BacktestService()
        results = []
        for name in names:
            try:
                results.append(service.run(
                    code=req.code, strategy=name, days=req.days,
                    initial_capital=req.initial_capital,
                ))
            except Exception as e:
                logger.warning(f"回测 {name} 失败: {e}")
        return [r.to_dict() for r in BacktestService.rank_results(results)]

    return ok({"rows": await run_in_threadpool(collect), "code": req.code})


@app.post("/api/backtest/portfolio")
async def backtest_portfolio(req: PortfolioBacktestRequest) -> dict:
    from app.models.stock import parse_stock_codes
    from app.services.backtest_service import BacktestService

    codes = parse_stock_codes(req.codes)
    if not codes:
        raise HTTPException(status_code=400, detail="未提供有效的股票代码")

    def collect():
        result = BacktestService().run_portfolio(
            codes, strategy=req.strategy, days=req.days,
            initial_capital=req.initial_capital,
        )
        if not result:
            return {}
        return {
            **{k: v for k, v in result.items() if k not in ("equity_curve", "details")},
            "equity_curve": df_records(result.get("equity_curve")),
            "details": [r.to_dict() for r in result.get("details", [])],
        }

    return ok(await run_in_threadpool(collect))


# ==================== P1：策略实验室 / AI 预测 ====================

class OptimizeRequest(BaseModel):
    code: str
    strategy: str = "ma_cross"
    days: int = Field(180, ge=60, le=1000)
    max_combos: int = Field(8, ge=1, le=20)
    folds: int = Field(3, ge=1, le=6)


@app.get("/api/lab/signals")
async def lab_signals(
    code: str = Query(...),
    days: int = Query(250, ge=60, le=1000),
) -> dict:
    from app.services.strategy_lab import StrategyLab

    return ok({"rows": await run_in_threadpool(StrategyLab().analyze_all, code, days)})


@app.post("/api/lab/optimize")
async def lab_optimize(req: OptimizeRequest) -> dict:
    from app.services.strategy_lab import StrategyLab

    def collect():
        lab = StrategyLab()
        return {
            "grid": lab.grid_search(req.code, req.strategy, days=req.days, max_combos=req.max_combos),
            "walk_forward": lab.walk_forward(
                req.code, req.strategy, days=req.days,
                n_splits=req.folds, max_combos=req.max_combos,
            ),
        }

    return ok(await run_in_threadpool(collect))


@app.get("/api/predict")
async def predict(
    code: str = Query(...),
    dl: bool = Query(False),
) -> dict:
    from app.ai.predictor_service import PredictorService

    def collect():
        # auto_train 固定 False：Web 侧绝不隐式训练模型
        return PredictorService().predict(code, use_dl=dl, auto_train=False)

    return ok(await run_in_threadpool(collect))


# ==================== P2：只读数据（预警 / 模拟盘 / 设置） ====================

# 测试可注入自定义 session scope，避免写操作碰到用户真实数据库
WRITE_SCOPE = None


def _alert_dto(a) -> dict:
    return {
        "id": a.id, "stock_code": a.stock_code, "stock_name": a.stock_name or "",
        "condition_type": a.condition_type, "condition_desc": a.condition_desc or "",
        "threshold": a.threshold, "is_active": bool(a.is_active),
        "is_triggered": bool(a.is_triggered), "repeat": bool(a.repeat),
        "note": a.note or "",
        "cooldown_minutes": a.cooldown_minutes,
        "last_triggered_at": a.last_triggered_at,
    }


@app.get("/api/alerts")
async def alerts() -> dict:
    from app.services.alert_service import AlertService

    def collect():
        return [_alert_dto(a) for a in AlertService().list_alerts()]

    return ok({"rows": await run_in_threadpool(collect)})


@app.get("/api/alert-types")
async def alert_types() -> dict:
    from app.services.alert_service import AlertService

    return ok({"items": await run_in_threadpool(AlertService.get_condition_types)})


@app.get("/api/paper")
async def paper() -> dict:
    from dataclasses import asdict

    from app.services.paper_broker import PaperBroker

    def collect():
        broker = PaperBroker()
        return {
            "summary": broker.summary(),
            "positions": [asdict(p) for p in broker.positions()],
            "orders": [asdict(o) for o in broker.orders(limit=20)],
        }

    return ok(await run_in_threadpool(collect))


# 设置页只展示这些字段；含密钥的字段一律不回传明文
SETTING_FIELDS = [
    ("database.path", "数据库路径", False),
    ("stock_data.bin_path", "行情程序", False),
    ("web.host", "Web 监听地址", False),
    ("web.port", "Web 端口", False),
    ("features.order_enabled", "订单执行层（冻结）", False),
    ("broker.enabled", "券商通道 kill switch", False),
    ("ai.llm.provider", "LLM 厂商", False),
    ("ai.llm.api_key", "LLM API Key", True),
    ("ai.quality.random_baseline", "模型随机基线", False),
    ("risk.max_order_amount", "单笔风控上限", False),
    ("risk.max_daily_amount", "单日风控上限", False),
    ("notification.on_trade", "成交推送", False),
    ("notification.pushplus.token", "PushPlus Token", True),
]


def _get_path(cfg: dict, path: str):
    node = cfg
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


@app.get("/api/settings")
async def settings() -> dict:
    cfg = get_config()
    rows = []
    for path, label, sensitive in SETTING_FIELDS:
        value = _get_path(cfg, path)
        env_key = "STOCK_AI_" + "__".join(p.upper() for p in path.split("."))
        rows.append({
            "key": path,
            "label": label,
            "value": ("已配置" if value else "未配置") if sensitive else value,
            "sensitive": sensitive,
            "env_key": env_key,
            "env_set": env_key in os.environ,
        })
    return ok({
        "rows": rows,
        "note": "设置页只读。密钥请使用环境变量配置，页面不会显示明文。",
    })


# ==================== P2：写操作（二次确认 + 幂等） ====================

class WriteBase(BaseModel):
    confirm: bool = False
    client_id: str = Field(..., min_length=8, max_length=64)


class TradeWrite(WriteBase):
    action: str = Field("buy", pattern="^(buy|sell)$")
    code: str
    price: float = Field(..., gt=0)
    quantity: int = Field(..., gt=0)
    name: str = ""
    reason: str = ""
    strategy: str = ""


class AlertWrite(WriteBase):
    op: str = Field(..., pattern="^(add|toggle|delete|reset)$")
    alert_id: int = 0
    code: str = ""
    condition_type: str = ""
    threshold: float | None = None
    repeat: bool = False
    note: str = ""


class PaperWrite(WriteBase):
    op: str = Field(..., pattern="^(buy|sell|reset)$")
    code: str = ""
    price: float = 0.0
    quantity: int = 0
    initial_cash: float = 0.0


async def _write(req: WriteBase, endpoint: str, fn: Callable[[], Any]) -> dict:
    from app.web.writes import WriteConflict, WriteRejected, execute_write

    def collect():
        return execute_write(
            client_id=req.client_id,
            endpoint=endpoint,
            payload=req.model_dump(),
            fn=fn,
            scope=WRITE_SCOPE,
        )

    try:
        return ok(await run_in_threadpool(collect))
    except WriteRejected as e:
        raise HTTPException(status_code=400, detail=str(e))
    except WriteConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/write/trade")
async def write_trade(req: TradeWrite) -> dict:
    from app.services.portfolio_service import PortfolioService
    from app.services.trade_service import TradeService

    def execute():
        trade = TradeService().add_trade(
            stock_code=req.code, action=req.action, price=req.price,
            quantity=req.quantity, stock_name=req.name,
            reason=req.reason, strategy=req.strategy,
        )
        try:
            PortfolioService().rebuild_portfolio()
        except Exception as e:
            logger.warning(f"持仓重算失败（交易已记录）: {e}")
        return {
            "id": trade.id, "stock_code": trade.stock_code,
            "action": trade.action, "price": trade.price,
            "quantity": trade.quantity, "amount": trade.amount,
        }

    return await _write(req, "trade", execute)


@app.post("/api/write/alert")
async def write_alert(req: AlertWrite) -> dict:
    from app.services.alert_service import AlertService

    def execute():
        service = AlertService()
        if req.op == "add":
            if not req.code or not req.condition_type:
                raise ValueError("新增预警需要 code 与 condition_type")
            alert = service.add_alert(
                stock_code=req.code, condition_type=req.condition_type,
                threshold=req.threshold, repeat=req.repeat, note=req.note,
            )
            return {"op": "add", "id": alert.id, "code": alert.stock_code}
        if not req.alert_id:
            raise ValueError("该操作需要 alert_id")

        if req.op == "toggle":
            result = service.toggle_alert(req.alert_id)
            return {"op": "toggle", "id": req.alert_id,
                    "is_active": bool(result.is_active) if result else None}
        if req.op == "delete":
            return {"op": "delete", "id": req.alert_id,
                    "deleted": service.delete_alert(req.alert_id)}
        result = service.reset_alert(req.alert_id)
        return {"op": "reset", "id": req.alert_id, "ok": result is not None}

    return await _write(req, "alert", execute)


@app.post("/api/write/paper")
async def write_paper(req: PaperWrite) -> dict:
    from dataclasses import asdict

    from app.services.paper_broker import PaperBroker

    def execute():
        broker = PaperBroker()
        if req.op == "reset":
            broker.reset(initial_cash=req.initial_cash or None)
            return {"op": "reset", "initial_cash": broker.account.initial_cash}
        if not req.code or req.price <= 0:
            raise ValueError("下单需要 code 与有效的 price")

        if req.op == "buy":
            order = broker.buy(req.code, req.price, quantity=req.quantity)
        else:
            order = broker.sell(req.code, req.price, quantity=req.quantity)
        return {"op": req.op, "order": asdict(order)}

    return await _write(req, "paper", execute)


# ==================== 持仓手工校正 ====================

class PortfolioWrite(WriteBase):
    op: str = Field("edit", pattern="^(edit|clear|unlock|rebuild)$")
    code: str = ""
    quantity: int | None = Field(None, ge=0)
    avg_cost: float | None = Field(None, ge=0)
    name: str | None = None
    reason: str = ""


@app.post("/api/write/portfolio")
async def write_portfolio(req: PortfolioWrite) -> dict:
    """手工校正持仓 / 解除锁定 / 从交易全量重建

    - edit: 改数量与成本价，并把该行标记为 manual_override（重建时跳过）；
      代码不存在时按 quantity / avg_cost 手工新增一条持仓
    - clear: 手工清仓（数量置 0 并锁定）
    - unlock: 解除锁定并立即按交易记录恢复
    - rebuild: 强制全量重建，会清除所有手工校正（危险操作，必须确认）
    """
    from app.services.portfolio_service import PortfolioService

    def execute():
        service = PortfolioService()
        if req.op == "rebuild":
            service.rebuild_portfolio(force=True)
            return {"op": "rebuild", "locked_cleared": True}

        if not req.code:
            raise ValueError("该操作需要股票代码 code")

        if req.op == "edit":
            if req.quantity is None and req.avg_cost is None and req.name is None:
                raise ValueError("校正至少需要 quantity / avg_cost / name 之一")
            return {"op": "edit", **service.update_holding(
                req.code, quantity=req.quantity, avg_cost=req.avg_cost,
                stock_name=req.name, reason=req.reason,
            )}

        if req.op == "clear":
            return {"op": "clear", **service.clear_holding(req.code, reason=req.reason)}

        return {"op": "unlock", **service.unlock_holding(req.code)}

    return await _write(req, "portfolio", execute)


# ==================== 自选股编辑（新增 / 移除 / 改备注） ====================

class WatchlistWrite(WriteBase):
    op: str = Field("add", pattern="^(add|remove|note)$")
    code: str = ""
    note: str = ""


@app.post("/api/write/watchlist")
async def write_watchlist(req: WatchlistWrite) -> dict:
    """编辑我的自选：新增 / 移除 / 改备注

    与交易录入、持仓校正一样走 confirm + web_writes 幂等。
    remove 是软删除（is_watched=False），保留股票基础信息与历史备注。
    """
    from app.services.watchlist_service import WatchlistService

    def execute():
        if not req.code:
            raise ValueError("该操作需要股票代码 code")
        service = WatchlistService()

        if req.op == "add":
            stock = service.add_watch(req.code, note=req.note)
            return {"op": "add", "code": stock.code, "name": stock.name or ""}

        if req.op == "remove":
            return {"op": "remove", "code": req.code,
                    "removed": service.remove_watch(req.code)}

        return {"op": "note", "code": req.code,
                "updated": service.update_note(req.code, req.note)}

    return await _write(req, "watchlist", execute)


# 静态资源挂在最后，避免覆盖 API 路由
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    page = STATIC_DIR / "index.html"
    if not page.exists():
        return HTMLResponse("<h1>前端资源缺失，请检查 app/web/static/</h1>", status_code=500)
    return FileResponse(page, media_type="text/html")
