"""领域层：依赖方向必须是 services/ai → domain"""

from app.domain import FeatureEngine
from app.domain.indicators import FeatureEngine as DomainFeatureEngine


def test_legacy_feature_engine_path_still_works():
    """旧导入路径 app.ai.feature_engine 仅做兼容，指向同一个类"""
    from app.ai.feature_engine import FeatureEngine as LegacyFeatureEngine

    assert LegacyFeatureEngine is DomainFeatureEngine
    assert FeatureEngine is DomainFeatureEngine


def test_domain_layer_has_no_upstream_dependency():
    """domain 不能反向依赖 services / ai / data"""
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent / "app" / "domain"
    forbidden = ("from app.services", "from app.ai", "from app.data", "from app.commands")

    for path in root.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for bad in forbidden:
            assert bad not in text, f"{path.name} 不应依赖 {bad}"
