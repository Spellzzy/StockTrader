"""本地 Web UI — JSON API 层

只做适配，不写业务逻辑：所有数据都来自现有 services / domain / data。
同步的 sqlite + 行情子进程调用统一走 run_in_threadpool，避免阻塞事件循环。
"""

from __future__ import annotations

import logging
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
async def portfolio() -> dict:
    from app.services.portfolio_service import PortfolioService

    def collect():
        service = PortfolioService()
        return {
            "holdings": service.get_portfolio_with_market_data(),
            "summary": service.get_total_summary(),
        }

    return ok(await run_in_threadpool(collect))


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


# 静态资源挂在最后，避免覆盖 API 路由
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    page = STATIC_DIR / "index.html"
    if not page.exists():
        return HTMLResponse("<h1>前端资源缺失，请检查 app/web/static/</h1>", status_code=500)
    return FileResponse(page, media_type="text/html")
