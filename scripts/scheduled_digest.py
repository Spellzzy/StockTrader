#!/usr/bin/env python
"""定时智能巡检脚本

可通过 Windows 计划任务 / crontab / systemd timer 等定时调用。

使用方式:
    # 直接运行（生成 + 推送）
    python scripts/scheduled_digest.py

    # 附加参数
    python scripts/scheduled_digest.py --dl --llm --auto-alert

    # 仅预览（不推送）
    python scripts/scheduled_digest.py --no-push

定时任务配置示例:

    Windows 计划任务 (schtasks) —— 必须用绝对路径，计划任务的默认工作目录是 System32:
        schtasks /create /tn "StockAI_AM" /tr "\"C:\\...\\python.exe\" \"C:\\...\\scripts\\scheduled_digest.py\"" /sc daily /st 10:00 /f
        schtasks /create /tn "StockAI_PM" /tr "\"C:\\...\\python.exe\" \"C:\\...\\scripts\\scheduled_digest.py\"" /sc daily /st 14:30 /f

    Linux crontab:
        0 10 * * 1-5 cd /path/to/stock-trader-ai && python scripts/scheduled_digest.py >> logs/digest.log 2>&1
        30 14 * * 1-5 cd /path/to/stock-trader-ai && python scripts/scheduled_digest.py >> logs/digest.log 2>&1
"""

import sys
import os
import argparse
import logging
from datetime import datetime

# 确保项目根目录在 Python 路径中
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
os.chdir(project_root)

# 路径插入之后再导入，保证直接 python scripts/scheduled_digest.py 也能找到 app
from app.domain.report_persist import persist_daily_reports

# 修复 Windows 编码
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def setup_logging():
    """配置日志（统一走 app.logging_setup，密钥自动打码）"""
    from app.logging_setup import setup_logging as _setup

    log_file = f"digest_{datetime.now().strftime('%Y%m%d')}.log"
    _setup(level="INFO", log_dir=os.path.join(project_root, "logs"), log_file=log_file)
    return logging.getLogger("scheduled_digest")


def is_trading_day() -> bool:
    """是否为交易日

    走 domain/calendar：周末 + config.yaml 里 market.holidays / market.workdays。
    法定节假日需要人工维护（交易所每年公告）。
    """
    from app.domain.calendar import get_calendar

    return get_calendar().is_trading_day()


def main():
    parser = argparse.ArgumentParser(description="Stock Trader AI 定时智能日报")
    parser.add_argument("--dl", action="store_true", help="使用深度学习模型")
    parser.add_argument("--llm", action="store_true", help="追加 LLM 深度分析")
    parser.add_argument("--no-push", action="store_true", help="不推送（仅生成并打印）")
    parser.add_argument("--auto-alert", action="store_true", help="自动配置高风险预警")
    parser.add_argument("--force", action="store_true", help="非交易日也强制执行")
    parser.add_argument("--top", type=int, default=3, help="LLM 分析看涨 Top N")
    parser.add_argument("--bottom", type=int, default=2, help="LLM 分析看跌 Top N")
    parser.add_argument("--no-html", action="store_true", help="不生成可视化 HTML 报告")
    parser.add_argument("--report-dir", default="", help="报告输出目录")
    args = parser.parse_args()

    logger = setup_logging()

    # 交易日检测
    if not args.force and not is_trading_day():
        logger.info("今天不是交易日，跳过。使用 --force 强制执行")
        return

    logger.info("=" * 60)
    logger.info("开始生成智能日报")
    logger.info(f"参数: dl={args.dl}, llm={args.llm}, push={not args.no_push}")

    digest = None
    try:
        # 初始化数据库
        from app.db.database import init_db
        init_db()

        from app.services.smart_digest import SmartDigestService
        svc = SmartDigestService()

        # 检查自选股
        watched = svc.watchlist.list_watched()
        if not watched:
            logger.warning("自选股列表为空，跳过")
            return

        logger.info(f"自选股数量: {len(watched)}")

        # 生成日报
        if args.no_push:
            digest = svc.generate(
                use_dl=args.dl,
                use_llm=args.llm,
                top_n=args.top,
                bottom_n=args.bottom,
            )
            if digest:
                logger.info("日报生成成功（未推送）")
                # 打印 Markdown 摘要到日志
                logger.info("\n" + digest["summary_text"])
            else:
                logger.error("日报生成失败")
        else:
            result = svc.generate_and_push(
                use_dl=args.dl,
                use_llm=args.llm,
                top_n=args.top,
                bottom_n=args.bottom,
            )
            digest = result["digest"]
            push_results = result["push_results"]

            if digest:
                bull = len(digest["bullish"])
                bear = len(digest["bearish"])
                neut = len(digest["neutral"])
                logger.info(
                    f"日报生成成功: {digest['total']}只 — "
                    f"{bull}涨 {neut}平 {bear}跌"
                )

                # 推送结果
                for ch_name, success, err in push_results:
                    if success:
                        logger.info(f"✅ {ch_name} 推送成功")
                    else:
                        logger.error(f"❌ {ch_name} 推送失败: {err}")

                if not push_results:
                    logger.warning("无可用推送渠道")
            else:
                logger.error("日报生成失败")

        # 落盘（推送之外留一份可回溯的文件）
        if digest:
            paths = persist_daily_reports(
                digest,
                output_dir=args.report_dir or os.path.join(project_root, "data", "reports"),
                with_html=not args.no_html,
            )
            for kind, path in paths.items():
                logger.info(f"日报已落盘 [{kind}]: {path}")
            if not paths:
                logger.error("日报落盘失败，请检查 data/reports 目录权限")

        # 自动预警
        if args.auto_alert and digest:
            new_alerts = svc.auto_configure_alerts(digest)
            if new_alerts:
                logger.info(f"已为 {len(new_alerts)} 只高风险股票自动配置预警")
                for a in new_alerts:
                    logger.info(f"  ⚠️ {a['name']} ({a['code']}) — 跌幅超 {abs(a['threshold'])}%")
            else:
                logger.info("无需新增自动预警")

    except Exception as e:
        logger.exception(f"定时日报执行异常: {e}")
        sys.exit(1)

    logger.info("智能日报任务完成")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
