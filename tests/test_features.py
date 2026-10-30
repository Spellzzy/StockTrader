"""特征工程（技术指标）"""

from app.ai.feature_engine import FeatureEngine

REQUIRED_COLUMNS = [
    "ma5", "ma10", "ma20", "ma60", "ma_bull",
    "ema12", "ema26",
    "macd_dif", "macd_dea", "macd_hist", "macd_cross",
    "rsi6", "rsi12", "rsi24",
    "kdj_k", "kdj_d", "kdj_j",
    "roc6", "roc12", "wr14",
    "boll_upper", "boll_mid", "boll_lower", "boll_pct",
    "atr", "atr_pct",
    "vol_ratio", "obv", "vol_ma5", "vol_ma20",
    "body", "amplitude", "bias5", "bias20",
    "return_1d", "return_5d",
]


def test_build_features_produces_required_columns(kline_df):
    out = FeatureEngine().build_features(kline_df)
    missing = [c for c in REQUIRED_COLUMNS if c not in out.columns]
    assert missing == []


def test_build_features_dropna_removes_all_nan(kline_df):
    out = FeatureEngine().build_features(kline_df, dropna=True)
    assert not out.isna().any().any()


def test_macd_cross_only_takes_three_values(kline_df):
    out = FeatureEngine().build_features(kline_df)
    assert set(out["macd_cross"].unique()) <= {-1, 0, 1}


def test_label_classification_drops_tail_by_horizon(kline_df):
    df = FeatureEngine().build_features(kline_df)
    labeled = FeatureEngine.add_label_classification(df, horizon=5, threshold=2.0)
    assert len(labeled) == len(df) - 5
    assert set(labeled["label"].unique()) <= {-1, 0, 1}


def test_get_feature_columns_excludes_price_and_label(kline_df):
    df = FeatureEngine.add_label_classification(FeatureEngine().build_features(kline_df))
    cols = FeatureEngine().get_feature_columns(df)
    for excluded in ("date", "label", "open", "close", "high", "low", "volume"):
        assert excluded not in cols
    assert "ma5" in cols
