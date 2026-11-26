"""回测策略模块 — 内置经典交易策略

每个策略实现 generate_signals() 方法，输入含技术指标的 DataFrame，
输出带 signal 列的 DataFrame:
    signal = 1  → 买入
    signal = -1 → 卖出
    signal = 0  → 持有/空仓
"""

import ast
import importlib.util
import inspect
import logging
import re
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


class BaseStrategy(ABC):
    """策略基类"""

    name: str = "base"
    description: str = "基础策略"

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """生成交易信号

        Args:
            df: 含技术指标的 DataFrame (由 FeatureEngine.build_features 产出)

        Returns:
            添加了 signal 列的 DataFrame
        """
        ...

    def __repr__(self) -> str:
        return f"<Strategy({self.name}: {self.description})>"


class MACDCrossStrategy(BaseStrategy):
    """MACD 金叉死叉策略

    - 金叉 (DIF 上穿 DEA): 买入
    - 死叉 (DIF 下穿 DEA): 卖出
    """

    name = "macd_cross"
    description = "MACD金叉买入/死叉卖出"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["signal"] = 0
        df.loc[df["macd_cross"] == 1, "signal"] = 1   # 金叉买入
        df.loc[df["macd_cross"] == -1, "signal"] = -1  # 死叉卖出
        return df


class MACrossStrategy(BaseStrategy):
    """均线突破策略

    - 短期均线上穿长期均线: 买入
    - 短期均线下穿长期均线: 卖出
    """

    name = "ma_cross"
    description = "均线金叉买入/死叉卖出"

    def __init__(self, short: int = 5, long: int = 20):
        self.short = short
        self.long = long
        self.description = f"MA{short}/MA{long} 均线交叉"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        short_col = f"ma{self.short}"
        long_col = f"ma{self.long}"

        if short_col not in df.columns or long_col not in df.columns:
            # 自行计算
            df[short_col] = df["close"].rolling(self.short).mean()
            df[long_col] = df["close"].rolling(self.long).mean()

        df["signal"] = 0
        # 金叉：短均线从下方穿越长均线
        cross_up = (df[short_col] > df[long_col]) & (df[short_col].shift(1) <= df[long_col].shift(1))
        cross_down = (df[short_col] < df[long_col]) & (df[short_col].shift(1) >= df[long_col].shift(1))
        df.loc[cross_up, "signal"] = 1
        df.loc[cross_down, "signal"] = -1
        return df


class RSIOversoldStrategy(BaseStrategy):
    """RSI 超买超卖策略

    - RSI < oversold (默认 30): 买入
    - RSI > overbought (默认 70): 卖出
    """

    name = "rsi"
    description = "RSI超卖买入/超买卖出"

    def __init__(self, period: int = 6, oversold: float = 30.0, overbought: float = 70.0):
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self.description = f"RSI{period} <{oversold}买入 >{overbought}卖出"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        rsi_col = f"rsi{self.period}"
        if rsi_col not in df.columns:
            rsi_col = "rsi6"  # 回退到默认的 rsi6

        df["signal"] = 0
        # 从超卖区回升时买入（前一根在超卖区，当前穿越上来）
        df.loc[
            (df[rsi_col] > self.oversold) & (df[rsi_col].shift(1) <= self.oversold),
            "signal",
        ] = 1
        # 从超买区回落时卖出
        df.loc[
            (df[rsi_col] < self.overbought) & (df[rsi_col].shift(1) >= self.overbought),
            "signal",
        ] = -1
        return df


class BollBandStrategy(BaseStrategy):
    """布林带位置策略

    - 位置从 `low_zone` 下方回升: 买入
    - 位置从 `high_zone` 上方回落: 卖出

    位置 = (收盘价 - 下轨) / (上轨 - 下轨) × 100，0=下轨、100=上轨。
    默认 0/100 保持旧版「跌破下轨后回轨内 / 突破上轨后回落」口径。
    """

    name = "boll"
    description = "布林带下轨买入/上轨卖出"

    def __init__(self, low_zone: float = 0.0, high_zone: float = 100.0):
        self.low_zone = float(low_zone)
        self.high_zone = float(high_zone)
        self.description = (
            f"布林带位置 P{self.low_zone:g} 回升买入 / P{self.high_zone:g} 回落卖出"
        )

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["signal"] = 0

        low, high = self.low_zone, self.high_zone
        if (
            low == 0
            and high == 100
            and {"close", "boll_lower", "boll_upper"}.issubset(df.columns)
        ):
            # 默认口径沿用旧版穿越上下轨，避免 boll_pct 的 1e-10  epsilon 造成边界差异
            buy = (df["close"] > df["boll_lower"]) & (
                df["close"].shift(1) <= df["boll_lower"].shift(1)
            )
            sell = (df["close"] < df["boll_upper"]) & (
                df["close"].shift(1) >= df["boll_upper"].shift(1)
            )
        else:
            if "boll_pct" in df.columns:
                pct = df["boll_pct"] * 100  # FeatureEngine 产出的是 0~1
            elif {"close", "boll_lower", "boll_upper"}.issubset(df.columns):
                pct = (
                    (df["close"] - df["boll_lower"])
                    / (df["boll_upper"] - df["boll_lower"] + 1e-10)
                    * 100
                )
            else:
                return df
            buy = (pct > low) & (pct.shift(1) <= low)
            sell = (pct < high) & (pct.shift(1) >= high)

        df.loc[buy, "signal"] = 1
        df.loc[sell, "signal"] = -1
        return df


class KDJCrossStrategy(BaseStrategy):
    """KDJ 金叉死叉策略

    - K线上穿D线 (在低位更佳): 买入
    - K线下穿D线 (在高位更佳): 卖出
    """

    name = "kdj"
    description = "KDJ金叉买入/死叉卖出"

    def __init__(self, low_zone: float = 30.0, high_zone: float = 70.0):
        self.low_zone = low_zone
        self.high_zone = high_zone

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["signal"] = 0

        if "kdj_k" not in df.columns or "kdj_d" not in df.columns:
            return df

        # 金叉: K 上穿 D
        cross_up = (df["kdj_k"] > df["kdj_d"]) & (df["kdj_k"].shift(1) <= df["kdj_d"].shift(1))
        # 死叉: K 下穿 D
        cross_down = (df["kdj_k"] < df["kdj_d"]) & (df["kdj_k"].shift(1) >= df["kdj_d"].shift(1))

        # 低位金叉更可靠
        df.loc[cross_up & (df["kdj_k"] < self.low_zone), "signal"] = 1
        # 高位死叉更可靠
        df.loc[cross_down & (df["kdj_k"] > self.high_zone), "signal"] = -1
        return df


class DualMACDStrategy(BaseStrategy):
    """双均线 + MACD 共振策略

    同时满足:
    - 均线多头排列 + MACD 金叉 → 买入
    - 均线跌破 + MACD 死叉 → 卖出
    """

    name = "dual_macd"
    description = "均线+MACD双重确认"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["signal"] = 0

        # 买入: 均线多头 + MACD 金叉
        buy_cond = (df.get("ma_bull", pd.Series(0, index=df.index)) == 1) & (df["macd_cross"] == 1)
        # 卖出: 均线空头 + MACD 死叉
        sell_cond = (df.get("ma_bull", pd.Series(0, index=df.index)) == 0) & (df["macd_cross"] == -1)

        if "ma_bull" in df.columns:
            buy_cond = (df["ma_bull"] == 1) & (df["macd_cross"] == 1)
            sell_cond = (df["ma_bull"] == 0) & (df["macd_cross"] == -1)

        df.loc[buy_cond, "signal"] = 1
        df.loc[sell_cond, "signal"] = -1
        return df


class TurtleBreakoutStrategy(BaseStrategy):
    """海龟突破策略 (简化版)

    - 价格突破 N 日最高价: 买入
    - 价格跌破 N 日最低价: 卖出
    """

    name = "turtle"
    description = "海龟突破策略"

    def __init__(self, entry_period: int = 20, exit_period: int = 10):
        self.entry_period = entry_period
        self.exit_period = exit_period
        self.description = f"突破{entry_period}日高点买入/{exit_period}日低点卖出"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["signal"] = 0

        # N日最高价/最低价 (不含当天)
        df["high_n"] = df["high"].shift(1).rolling(self.entry_period).max()
        df["low_n"] = df["low"].shift(1).rolling(self.exit_period).min()

        # 突破买入
        df.loc[df["close"] > df["high_n"], "signal"] = 1
        # 跌破卖出
        df.loc[df["close"] < df["low_n"], "signal"] = -1

        # 清理临时列
        df.drop(columns=["high_n", "low_n"], inplace=True)
        return df


# ==================== 策略注册表 ====================

BUILTIN_STRATEGIES = {
    "macd_cross": MACDCrossStrategy,
    "ma_cross": MACrossStrategy,
    "rsi": RSIOversoldStrategy,
    "boll": BollBandStrategy,
    "kdj": KDJCrossStrategy,
    "dual_macd": DualMACDStrategy,
    "turtle": TurtleBreakoutStrategy,
}


_CUSTOM_STRATEGIES: dict[str, type[BaseStrategy]] = {}
_CUSTOM_PARAM_GRIDS: dict[str, dict] = {}
_CUSTOM_LOADED = False


def _custom_dir() -> Optional[Path]:
    """自定义策略目录；关闭或不存在时返回 None"""
    from app.config import PROJECT_ROOT, get_config

    cfg = get_config().get("strategies") or {}
    if not cfg.get("enabled", True):
        return None
    path = Path(str(cfg.get("dir") or "./strategies"))
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load_custom_strategies() -> None:
    """扫描目录下的 .py，自动注册 BaseStrategy 子类（只加载一次）"""
    global _CUSTOM_LOADED
    if _CUSTOM_LOADED:
        return
    _CUSTOM_LOADED = True

    directory = _custom_dir()
    if directory is None or not directory.is_dir():
        return

    for path in sorted(directory.glob("*.py")):
        if path.name.startswith("_"):
            continue
        module_name = f"_stock_ai_strategy_{abs(hash(str(path)))}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        except Exception as e:
            logger.warning("加载自定义策略 %s 失败: %s", path.name, e)
            sys.modules.pop(module_name, None)
            continue

        grids = getattr(module, "PARAM_GRIDS", None)
        grids = grids if isinstance(grids, dict) else {}
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if not issubclass(obj, BaseStrategy) or obj is BaseStrategy:
                continue
            if inspect.isabstract(obj):
                continue
            name = getattr(obj, "name", "")
            if not isinstance(name, str) or not name.strip():
                continue
            name = name.strip()
            if name in BUILTIN_STRATEGIES or name in _CUSTOM_STRATEGIES:
                logger.warning(f"自定义策略 {name} 与已有策略重名，已跳过")
                continue
            _CUSTOM_STRATEGIES[name] = obj
            params = grids.get(name)
            if isinstance(params, dict):
                _CUSTOM_PARAM_GRIDS[name] = params


def _all_strategies() -> dict[str, type[BaseStrategy]]:
    _load_custom_strategies()
    return {**BUILTIN_STRATEGIES, **_CUSTOM_STRATEGIES}


def coerce_strategy_params(params: dict) -> dict:
    """把 CLI / Web 传来的字符串参数转成数字或布尔，供策略构造函数使用。"""
    result = {}
    for key, raw in (params or {}).items():
        name = str(key).strip()
        if not name:
            continue
        if isinstance(raw, bool):
            result[name] = raw
            continue
        if isinstance(raw, (int, float)):
            result[name] = raw
            continue
        text = str(raw).strip()
        lowered = text.lower()
        if lowered in ("true", "false"):
            result[name] = lowered == "true"
            continue
        try:
            result[name] = int(text)
        except ValueError:
            try:
                result[name] = float(text)
            except ValueError:
                result[name] = text
    return result


def get_custom_param_grids() -> dict[str, dict]:
    """自定义策略的参数网格，供 strategy_lab 的 optimize 使用"""
    _load_custom_strategies()
    return dict(_CUSTOM_PARAM_GRIDS)


def reset_custom_strategies() -> None:
    """清空自定义策略缓存（测试用；运行时重新扫描需重启进程）"""
    global _CUSTOM_LOADED
    _CUSTOM_STRATEGIES.clear()
    _CUSTOM_PARAM_GRIDS.clear()
    _CUSTOM_LOADED = False


_CUSTOM_FILENAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*\.py$")


def _strategy_file_path(filename: str) -> Path:
    """校验自定义策略文件名，返回目录内的安全路径"""
    if not isinstance(filename, str) or not _CUSTOM_FILENAME_RE.fullmatch(filename):
        raise ValueError("文件名只能为字母开头、仅含字母数字下划线的 .py 文件")
    directory = _custom_dir()
    if directory is None:
        raise ValueError("自定义策略已在配置中禁用")
    directory.mkdir(parents=True, exist_ok=True)
    path = (directory / filename).resolve()
    if path.parent != directory.resolve():
        raise ValueError("非法文件路径")
    return path


def _declared_strategies(source: str) -> list[dict]:
    """静态解析源码中声明的策略（不执行用户代码）"""
    tree = ast.parse(source)
    declared = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        name = None
        description = ""
        has_signals = False
        for stmt in node.body:
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                target = stmt.targets[0]
                if isinstance(target, ast.Name) and isinstance(stmt.value, ast.Constant):
                    if target.id == "name" and isinstance(stmt.value.value, str):
                        name = stmt.value.value.strip()
                    if target.id == "description" and isinstance(stmt.value.value, str):
                        description = stmt.value.value.strip()
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name == "generate_signals":
                has_signals = True
        if name and has_signals:
            declared.append({"name": name, "description": description, "class": node.name})
    return declared


def list_custom_strategy_files() -> list[dict]:
    """列出 strategies/ 目录下的可编辑策略文件（含源码）"""
    directory = _custom_dir()
    if directory is None or not directory.is_dir():
        return []
    items = []
    for path in sorted(directory.glob("*.py")):
        if path.name.startswith("_") or not _CUSTOM_FILENAME_RE.fullmatch(path.name):
            continue
        try:
            source = path.read_text(encoding="utf-8")
            declared = _declared_strategies(source)
        except (OSError, SyntaxError, ValueError) as e:
            items.append({"filename": path.name, "source": "", "strategies": [], "error": str(e)})
            continue
        items.append({
            "filename": path.name,
            "source": source,
            "strategies": declared,
            "error": "" if declared else "未找到含 name 与 generate_signals 的策略类",
        })
    return items


def save_custom_strategy(filename: str, source: str) -> dict:
    """校验并写入策略源码，随后热重载注册表。"""
    path = _strategy_file_path(filename)
    if not isinstance(source, str) or len(source) > 200_000:
        raise ValueError("策略源码不能为空且不能超过 200KB")
    try:
        compile(source, filename, "exec")
        declared = _declared_strategies(source)
    except SyntaxError as e:
        raise ValueError(f"语法错误（第 {e.lineno} 行）: {e.msg}") from e
    if not declared:
        raise ValueError("未找到含 name 与 generate_signals 的策略类")

    names = [item["name"] for item in declared]
    if len(set(names)) != len(names):
        raise ValueError("文件内策略名重复")
    for name in names:
        if name in BUILTIN_STRATEGIES:
            raise ValueError(f"策略名 {name} 与内置策略冲突")
    for item in list_custom_strategy_files():
        if item["filename"] == filename:
            continue
        for other in item["strategies"]:
            if other["name"] in names:
                raise ValueError(f"策略名 {other['name']} 已存在于 {item['filename']}")

    path.write_text(source, encoding="utf-8", newline="\n")
    reset_custom_strategies()
    _load_custom_strategies()
    missing = [name for name in names if name not in _CUSTOM_STRATEGIES]
    if missing:
        path.unlink(missing_ok=True)
        reset_custom_strategies()
        raise ValueError(f"策略注册失败: {', '.join(missing)}")
    return {"filename": filename, "strategies": declared, "items": list_strategies()}


def delete_custom_strategy(filename: str) -> dict:
    """删除自定义策略文件并热重载注册表"""
    path = _strategy_file_path(filename)
    if not path.exists():
        raise ValueError("策略文件不存在")
    path.unlink()
    reset_custom_strategies()
    _load_custom_strategies()
    return {"filename": filename, "items": list_strategies()}


def get_strategy(name: str, **kwargs) -> BaseStrategy:
    """根据名称获取策略实例（内置 + 自定义）

    Args:
        name: 策略名称，可用 `stock-ai bt-list` 查看
        **kwargs: 策略参数

    Returns:
        策略实例

    Raises:
        ValueError: 未知策略名称
    """
    strategies = _all_strategies()
    cls = strategies.get(name)
    if cls is None:
        valid = ", ".join(strategies.keys())
        raise ValueError(f"未知策略: {name}\n可用策略: {valid}")
    return cls(**kwargs)


def list_strategy_names() -> list[str]:
    """只返回策略名称（给需要遍历策略名的调用方用）

    `list_strategies()` 返回的是含 name/description/class 的 dict 列表，
    直接拿它当字符串用会报 unhashable type: 'dict'。
    """
    return list(_all_strategies().keys())


def list_strategies() -> list:
    """列出内置 + 自定义策略"""
    result = []
    for name, cls in _all_strategies().items():
        instance = cls()
        result.append({
            "name": name,
            "description": instance.description,
            "class": cls.__name__,
        })
    return result
