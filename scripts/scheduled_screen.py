#!/usr/bin/env python
"""定时全市场摘选脚本

流程：全A代码池 → 批量 quote 预筛 → 复用 screener 条件评估 → 结果落库 → 报告落盘 → 推送

使用方式:
    # 生成 + 推送（默认，交易日才跑）
    python scripts/scheduled_screen.py

    # 仅预览，不推送
    python scripts/scheduled_screen.py --no-push

    # 非交易日强制跑 / 换股票池 / 强制刷新全 A 缓存
    python scripts/scheduled_screen.py --force
    python scripts/scheduled_screen.py --pool watchlist
    python scripts/scheduled_screen.py --pool all_a:refresh

    # 只看历史扫描记录
    python scripts/scheduled_screen.py --history

Windows 计划任务（收盘后跑一次，必须用绝对路径）:
    schtasks /create /tn "StockAI_Screen" /tr "\"C:\\...\\python.exe\" \"C:\\...\\scripts\\scheduled_screen.py\"" /sc daily /st 15:30 /f

Linux crontab:
    30 15 * * 1-5 cd /path/to/stock-trader-ai && python scripts/scheduled_screen.py >> logs/screen.log 2>&1
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
os.chdir(project_root)

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

DEFAULT_REPORT_DIR = os.path.join(project_root, "data", "reports")


def setup_logging():
    from app.logging_setup import setup_logging as _setup

    _setup(
        level="INFO",
        log_dir=os.path.join(project_root, "logs"),
        log_file=f"screen_{datetime.now().strftime('%Y%m%d')}.log",
    )
    return logging.getLogger("scheduled_screen")


def is_trading_day() -> bool:
    from app.domain.calendar import get_calendar

    return get_calendar().is_trading_day()


# 报告渲染放在服务层，CLI 与定时脚本共用一份实现
from app.services.market_scan_service import build_report  # noqa: E402


def persist_report(result: dict, output_dir: str = "") -> str:
    out = Path(output_dir) if output_dir else Path(DEFAULT_REPORT_DIR)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"screen_{datetime.now().strftime('%Y%m%d')}.md"
    path.write_text(build_report(result), encoding="utf-8")
    return str(path)


def push_report(result: dict, report: str) -> list:
    from app.services.notification import NotificationLevel, NotificationManager

    notifier = NotificationManager()
    if not notifier.is_enabled:
        return []
    return notifier.notify(
        title=f"🔎 全市场摘选 {result.get('run_date', '')} · 命中 {result.get('hit_count', 0)} 只",
        content=report,
        level=NotificationLevel.INFO,
    )


def print_history(limit: int) -> None:
    from app.services.market_scan_service import MarketScanService

    rows = MarketScanService().list_runs(limit=limit)
    if not rows:
        print("暂无扫描记录")
        return
    print(f"{'ID':>4} {'日期':<12} {'池':<12} {'候选':>6} {'命中':>6} {'耗时(s)':>8}")
    for r in rows:
        print(f"{r['id']:>4} {r['run_date']:<12} {r['pool']:<12} "
              f"{r['candidate_count']:>6} {r['hit_count']:>6} "
              f"{r['duration_seconds']:>8.1f}")


def main():
    parser = argparse.ArgumentParser(description="Stock Trader AI 定时全市场摘选")
    parser.add_argument("--no-push", action="store_true", help="不推送（仅生成并落盘）")
    parser.add_argument("--force", action="store_true", help="非交易日也执行；并忽略今日同参数缓存")
    parser.add_argument("--pool", default="", help="覆盖股票池 all_a / watchlist / portfolio / file:...")
    parser.add_argument("--top", type=int, default=0, help="覆盖展示的 Top N")
    parser.add_argument("--report-dir", default="", help="报告输出目录")
    parser.add_argument("--no-save", action="store_true", help="不落库（调试用）")
    parser.add_argument("--history", action="store_true", help="只查看历史扫描记录")
    parser.add_argument("--history-limit", type=int, default=10, help="历史记录条数")
    args = parser.parse_args()

    logger = setup_logging()

    if args.history:
        print_history(args.history_limit)
        return

    if not args.force and not is_trading_day():
        logger.info("今天不是交易日，跳过。使用 --force 强制执行")
        return

    from app.db.database import init_db
    init_db()

    from app.services.market_scan_service import MarketScanService

    cfg = {}
    if args.top > 0:
        from app.config import get_config
        cfg = dict(get_config().get("market_scan", {}) or {})
        cfg["top_n"] = args.top

    svc = MarketScanService(config=cfg or None)
    logger.info("=" * 60)
    logger.info(f"开始全市场摘选 pool={args.pool or 'config'} force={args.force}")

    result = svc.run(
        pool=args.pool or None,
        force=args.force,
        save=not args.no_save,
        prefilter_cb=lambda done, total, found: (
            logger.info(f"预筛 {done}/{total}，通过 {found}") if done % 500 == 0 or done >= total else None
        ),
        screen_cb=lambda done, total, hits: (
            logger.info(f"条件评估 {done}/{total}，命中 {hits}") if done % 100 == 0 or done >= total else None
        ),
    )

    if result.get("cached"):
        logger.info(f"复用今日已有扫描 run #{result.get('id')}，未重跑")
        print(f"（复用今日已有扫描 run #{result.get('id')}，未重跑）\n")
    logger.info(
        f"扫描完成: {result['universe_count']} → {result['candidate_count']} 候选 → "
        f"{result['hit_count']} 命中，耗时 {result['duration_seconds']}s"
    )

    report = build_report(result)
    path = persist_report(result, output_dir=args.report_dir)
    logger.info(f"报告已落盘: {path}")

    if not args.no_push:
        try:
            for ch_name, success, err in push_report(result, report):
                logger.info(f"✅ {ch_name} 推送成功" if success else f"❌ {ch_name} 推送失败: {err}")
        except Exception as e:
            logger.warning(f"推送失败（不影响报告）: {e}")

    print(report)


if __name__ == "__main__":
    main()
