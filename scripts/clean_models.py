"""清理无效/重复的模型文件

背景：早期命令入口没有统一规范化股票代码，导致同一只股票同时存在
`605099_rf_20260408.joblib` 与 `sh605099_rf_20260408.joblib`；
另外指数（如 sh000001）也被拿来训练过模型，这类模型没有意义。

处理规则:
    1. 指数代码（sh000xxx / sz39xxxx）→ 删除
    2. 未带市场前缀，但已存在规范化版本 → 删除重复项
    3. 未带市场前缀且无对应规范化版本 → 改名为规范化代码
    4. 其余 → 保留

用法（默认只预览，加 --apply 才真正执行）:
    python scripts/clean_models.py
    python scripts/clean_models.py --apply
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path

if __package__ in (None, ""):  # 直接运行脚本时保证能 import app
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.platform == "win32":  # 避免 Windows 控制台乱码
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from app.models.stock import normalize_stock_code, is_index_code  # noqa: E402

MODEL_SUFFIXES = (".joblib", ".pt")
SUB_DIRS = ("ml", "dl")


@dataclass
class CleanupPlan:
    """清理计划（纯规划，apply() 才落盘）"""

    keep: list[Path] = field(default_factory=list)
    delete: list[Path] = field(default_factory=list)
    delete_reasons: dict[str, str] = field(default_factory=dict)
    rename: list[tuple[Path, Path]] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.delete and not self.rename

    def apply(self):
        """执行清理：先删重复项，再改名"""
        for path in self.delete:
            path.unlink(missing_ok=True)
        for src, dst in self.rename:
            if dst.exists():
                src.unlink(missing_ok=True)
            else:
                src.rename(dst)


def build_cleanup_plan(model_dir: Path) -> CleanupPlan:
    """扫描模型目录，生成清理计划"""
    plan = CleanupPlan()
    model_dir = Path(model_dir)

    for sub in SUB_DIRS:
        directory = model_dir / sub
        if not directory.is_dir():
            continue

        files = sorted(
            p for p in directory.iterdir()
            if p.is_file() and p.suffix in MODEL_SUFFIXES
        )
        existing = {p.name for p in files}

        for path in files:
            raw_code, _, rest = path.name.partition("_")
            if not rest:
                plan.keep.append(path)
                continue

            norm_code = normalize_stock_code(raw_code)

            if is_index_code(norm_code):
                plan.delete.append(path)
                plan.delete_reasons[path.name] = f"指数代码不训练模型 ({norm_code})"
                continue

            if norm_code == raw_code:
                plan.keep.append(path)
                continue

            target_name = f"{norm_code}_{rest}"
            if target_name in existing:
                plan.delete.append(path)
                plan.delete_reasons[path.name] = f"重复(保留规范化代码) → {target_name}"
            else:
                plan.rename.append((path, directory / target_name))

    return plan


def default_model_dir() -> Path:
    from app.config import get_config

    return Path(get_config().get("ai", {}).get("model", {}).get("save_dir", "./data/models"))


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="清理无效/重复的模型文件")
    parser.add_argument("--dir", default=None, help="模型目录，默认读取 config.yaml 的 ai.model.save_dir")
    parser.add_argument("--apply", action="store_true", help="真正执行删除/改名（默认只预览）")
    args = parser.parse_args(argv)

    model_dir = Path(args.dir) if args.dir else default_model_dir()
    if not model_dir.exists():
        print(f"模型目录不存在: {model_dir}")
        return 1

    plan = build_cleanup_plan(model_dir)

    print(f"模型目录: {model_dir}")
    print(f"保留 {len(plan.keep)} 个，待删除 {len(plan.delete)} 个，待改名 {len(plan.rename)} 个\n")

    for path in plan.delete:
        print(f"  [删除] {path.relative_to(model_dir)}  ← {plan.delete_reasons[path.name]}")
    for src, dst in plan.rename:
        print(f"  [改名] {src.relative_to(model_dir)} → {dst.name}")

    if plan.is_empty:
        print("没有需要清理的模型文件。")
        return 0

    if not args.apply:
        print("\n以上为预览，未做任何改动。确认无误后加 --apply 执行。")
        return 0

    plan.apply()
    print("\n清理完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
