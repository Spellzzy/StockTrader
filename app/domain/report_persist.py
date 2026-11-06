"""日报落盘

定时任务与 `digest run` / `digest push` 共用同一套文件名和正文。
上午、下午各一份，同一时段再次生成会覆盖；正文用 summary_text（含可信卡）。
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

DEFAULT_REPORT_DIR = "data/reports"
_logger = logging.getLogger("scheduled_digest")


def persist_daily_reports(digest: dict, output_dir: str = "", with_html: bool = True) -> dict:
    """把日报落到磁盘（推送之外还要留一份可回溯的文件）

    产出（带 am/pm 时段后缀，避免上午和下午两次任务互相覆盖）:
        digest_YYYYMMDD_am.md     Markdown 日报正文（summary_text）
        daily_YYYYMMDD_am.html    可视化报告（图表内嵌）

    任一块失败只记日志，不影响另一块，也不影响推送。
    目录创建失败会向上抛，由调用方决定是否中断。
    """
    out = Path(output_dir) if output_dir else Path(DEFAULT_REPORT_DIR)
    out.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    stamp = now.strftime("%Y%m%d")
    slot = "am" if now.hour < 12 else "pm"
    paths = {}

    try:
        md_path = out / f"digest_{stamp}_{slot}.md"
        body = digest.get("summary_text") or ""
        md_path.write_text(
            f"# 智能日报 {now:%Y-%m-%d %H:%M} ({slot})\n\n{body}\n",
            encoding="utf-8",
        )
        paths["markdown"] = str(md_path)
    except Exception as e:
        _logger.warning(f"日报 Markdown 落盘失败: {e}")

    if with_html:
        try:
            from app.visualization.report import HTMLReport

            paths["html"] = HTMLReport(output_dir=str(out)).build(
                filename=f"daily_{stamp}_{slot}.html"
            )
        except Exception as e:
            _logger.warning(f"日报 HTML 落盘失败: {e}")

    return paths
