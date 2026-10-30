"""统一费率模型

交易录入与回测必须共用同一套费率，避免两处硬编码出现偏差。
费率从 config.yaml 的 fees 段读取，未配置时使用 A 股常见默认值。

用法:
    model = FeeModel.from_config(get_config())
    commission = model.commission(amount=100_000)
    tax = model.tax(amount=100_000, action="sell", market="A")
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class FeeModel:
    """费率模型（不可变）

    Attributes:
        commission_rate: 佣金费率（默认万3）
        min_commission: 单笔最低佣金（默认 5 元）
        stamp_tax_rate: 印花税率，仅 A 股卖出收取（默认千1）
    """

    commission_rate: float = 0.0003
    min_commission: float = 5.0
    stamp_tax_rate: float = 0.001

    @classmethod
    def from_config(cls, cfg: Optional[dict] = None) -> "FeeModel":
        """从配置构造，缺失项回落默认值"""
        fees = (cfg or {}).get("fees", {}) or {}
        return cls(
            commission_rate=float(fees.get("commission_rate", cls.commission_rate)),
            min_commission=float(fees.get("min_commission", cls.min_commission)),
            stamp_tax_rate=float(fees.get("stamp_tax_rate", cls.stamp_tax_rate)),
        )

    def commission(self, amount: float, market: str = "A") -> float:
        """佣金：按比例计算，不低于最低佣金"""
        if amount <= 0:
            return 0.0
        return max(amount * self.commission_rate, self.min_commission)

    def tax(self, amount: float, action: str = "sell", market: str = "A") -> float:
        """印花税：仅 A 股卖出收取"""
        if amount <= 0:
            return 0.0
        if market != "A":
            return 0.0
        if action != "sell":
            return 0.0
        return amount * self.stamp_tax_rate
