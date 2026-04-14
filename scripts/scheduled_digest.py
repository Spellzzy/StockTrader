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

    Windows 计划任务 (schtasks):
        schtasks /create /tn "StockAI_Digest_AM" /tr "python C:\\path\\to\\scripts\\scheduled_digest.py" /sc daily /st 10:00
        schtasks /create /tn "StockAI_Digest_PM" /tr "python C:\\path\\to\\scripts\\scheduled_digest.py" /sc daily /st 14:30

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

# 修复 Windows 编码
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def setup_logging():
    """配置日志"""
    log_dir = os.path.join(project_root, "logs")
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, f"digest_{datetime.now().strftime('%Y%m%d')}.log")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    return logging.getLogger("scheduled_digest")


def is_trading_day() -> bool:
    """简单判断是否为交易日（周一~周五，不含节假日）

    注意：此处仅做工作日判断，如需精确的 A 股交易日历，
    建议使用 exchange_calendars 库或自行维护节假日表。
    """
    today = datetime.now()
    # 周一=0 ... 周日=6
    return today.weekday() < 5


def main():
    parser = argparse.ArgumentParser(description="Stock Trader AI 定时智能日报")
    parser.add_argument("--dl", action="store_true", help="使用深度学习模型")
    parser.add_argument("--llm", action="store_true", help="追加 LLM 深度分析")
    parser.add_argument("--no-push", action="store_true", help="不推送（仅生成并打印）")
    parser.add_argument("--auto-alert", action="store_true", help="自动配置高风险预警")
    parser.add_argument("--force", action="store_true", help="非交易日也强制执行")
    parser.add_argument("--top", type=int, default=3, help="LLM 分析看涨 Top N")
    parser.add_argument("--bottom", type=int, default=2, help="LLM 分析看跌 Top N")
    args = parser.parse_args()

    logger = setup_logging()

    # 交易日检测
    if not args.force and not is_trading_day():
        logger.info("今天不是交易日，跳过。使用 --force 强制执行")
        return

    logger.info("=" * 60)
    logger.info("开始生成智能日报")
    logger.info(f"参数: dl={args.dl}, llm={args.llm}, push={not args.no_push}")

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
