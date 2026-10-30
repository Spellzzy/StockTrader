"""技术指标特征工程（已下沉到 app.domain.indicators）

保留本模块只是为了兼容旧的导入路径，实现统一在 app/domain/indicators.py。
新代码请直接从领域层导入:

    from app.domain.indicators import FeatureEngine
"""

from app.domain.indicators import FeatureEngine

__all__ = ["FeatureEngine"]
