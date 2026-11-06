"""日报落盘

定时任务与 `digest run` / `digest push` 共用同一套文件名。
上午、下午各一份，同一时段再次生成会覆盖。
Markdown 用 summary_text（含可信卡）；同 slot 另写一份瘦身 JSON 供回放。
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime
from pathlib import Path

DEFAULT_REPORT_DIR = "data/reports"
_logger = logging.getLogger("scheduled_digest")

_ITEM_KEYS = (
    "code",
    "name",
    "signal",
    "score",
    "confidence",
    "stars",
    "key_factors",
    "quality",
    "models_used",
)


def _slim_items(items) -> list:
    if not isinstance(items, list):
        return []
    slim = []
    for item in items:
        if not isinstance(item, dict):
            continue
        slim.append({key: item[key] for key in _ITEM_KEYS if key in item})
    return slim


def _digest_total(digest: dict, bullish: list, bearish: list, neutral: list) -> int:
    raw = digest.get("total")
    if isinstance(raw, bool):
        return len(bullish) + len(bearish) + len(neutral)
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float) and math.isfinite(raw) and raw.is_integer():
        return int(raw)
    return len(bullish) + len(bearish) + len(neutral)


def build_digest_snapshot(digest: dict, *, slot: str, now: datetime) -> dict:
    """结构化回放：日期、时段、总数，以及三类条目（条目保留 quality）。

    不写入 scan_results、summary_text、plain_text、llm_reports。
    """
    bullish = _slim_items(digest.get("bullish"))
    bearish = _slim_items(digest.get("bearish"))
    neutral = _slim_items(digest.get("neutral"))
    date = digest.get("date")
    if not isinstance(date, str) or not date.strip():
        date = now.strftime("%Y-%m-%d %H:%M")
    else:
        date = date.strip()
    return {
        "date": date,
        "slot": slot,
        "total": _digest_total(digest, bullish, bearish, neutral),
        "bullish": bullish,
        "bearish": bearish,
        "neutral": neutral,
    }


def persist_daily_reports(digest: dict, output_dir: str = "", with_html: bool = True) -> dict:
    """把日报落到磁盘（推送之外还要留一份可回溯的文件）

    产出（带 am/pm 时段后缀，避免上午和下午两次任务互相覆盖）:
        digest_YYYYMMDD_am.md     Markdown 日报正文（summary_text）
        digest_YYYYMMDD_am.json   瘦身结构化回放（不含整份 scan_results）
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
    payload = digest if isinstance(digest, dict) else {}

    try:
        md_path = out / f"digest_{stamp}_{slot}.md"
        body = payload.get("summary_text") or ""
        md_path.write_text(
            f"# 智能日报 {now:%Y-%m-%d %H:%M} ({slot})\n\n{body}\n",
            encoding="utf-8",
        )
        paths["markdown"] = str(md_path)
    except Exception as e:
        _logger.warning(f"日报 Markdown 落盘失败: {e}")

    try:
        json_path = out / f"digest_{stamp}_{slot}.json"
        snapshot = build_digest_snapshot(payload, slot=slot, now=now)
        json_path.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        paths["json"] = str(json_path)
    except Exception as e:
        _logger.warning(f"日报 JSON 落盘失败: {e}")

    if with_html:
        try:
            from app.visualization.report import HTMLReport

            paths["html"] = HTMLReport(output_dir=str(out)).build(
                filename=f"daily_{stamp}_{slot}.html"
            )
        except Exception as e:
            _logger.warning(f"日报 HTML 落盘失败: {e}")

    return paths
