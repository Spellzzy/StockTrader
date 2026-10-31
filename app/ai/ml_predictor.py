"""ML 预测器 — 基于经典机器学习的股票涨跌预测

使用 RandomForest 和 XGBoost 进行短期涨跌预测。
轻量、训练快、可解释性好。

用法:
    predictor = MLPredictor()
    result = predictor.train_and_predict("sh600519")
"""

import logging
from typing import Optional, Tuple

import numpy as np
import pandas as pd

from app.domain.indicators import FeatureEngine
from app.ai.model_manager import ModelManager
from app.ai.split import time_split_indices
from app.services.market_service import MarketService

logger = logging.getLogger(__name__)


class MLPredictor:
    """经典 ML 预测器 (RandomForest + XGBoost)"""

    def __init__(self):
        self.feature_engine = FeatureEngine()
        self.model_manager = ModelManager()
        self.market_service = MarketService()

    def _prepare_data(
        self,
        code: str,
        count: int = 800,
        horizon: int = 5,
        threshold: float = 2.0,
    ) -> Optional[pd.DataFrame]:
        """获取 K线 → 特征工程 → 添加标签

        Returns:
            含特征和 label 列的 DataFrame，失败返回 None
        """
        df = self.market_service.get_kline_df(code, period="day", count=count, adjust="qfq")
        if df is None or len(df) < 100:
            logger.warning(f"数据不足: {code}, 仅 {len(df) if df is not None else 0} 条")
            return None

        # 特征工程
        df = self.feature_engine.build_features(df, dropna=True)
        if len(df) < 80:
            logger.warning(f"特征工程后数据不足: {code}, 仅 {len(df)} 条")
            return None

        # 添加分类标签
        df = self.feature_engine.add_label_classification(df, horizon=horizon, threshold=threshold)
        return df

    @staticmethod
    def _window_dates(df: pd.DataFrame, window: slice) -> Tuple[Optional[str], Optional[str]]:
        """取某个切片的起止日期（用于记录训练区间）"""
        if "date" not in df.columns:
            return None, None
        dates = df["date"].iloc[window]
        if len(dates) == 0:
            return None, None
        return str(dates.iloc[0])[:10], str(dates.iloc[-1])[:10]

    @staticmethod
    def _expiry_timestamp() -> str:
        """按配置计算模型过期时间"""
        from datetime import datetime, timedelta

        from app.config import get_config

        days = int(get_config().get("ai", {}).get("model", {}).get("expire_days", 30))
        return (datetime.now() + timedelta(days=days)).isoformat()

    def walk_forward(
        self,
        code: str,
        n_splits: int = 3,
        count: int = 800,
        horizon: int = 5,
        threshold: float = 2.0,
        model_type: str = "rf",
        n_estimators: int = 100,
    ) -> Optional[dict]:
        """滚动窗口验证（walk-forward）

        按时间顺序把数据切成 n_splits+1 段，第 k 段用前 k 段训练、第 k+1 段测试，
        比一次性切分更能反映模型在真实滚动预测中的表现。

        Returns:
            {"code", "model_type", "folds": [...], "mean_accuracy"}
        """
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.metrics import accuracy_score

        df = self._prepare_data(code, count, horizon, threshold)
        if df is None:
            return None

        feature_cols = self.feature_engine.get_feature_columns(df)
        X = df[feature_cols].values
        y = df["label"].values

        n = len(X)
        fold_size = n // (n_splits + 1)
        if fold_size < 20:
            logger.warning(f"数据量不足以做 {n_splits} 折滚动验证: 仅 {n} 条")
            return None

        folds = []
        for k in range(1, n_splits + 1):
            train_end = fold_size * k
            test_end = min(fold_size * (k + 1), n)

            # 同样要留出标签 horizon 的间隔
            train_stop = train_end - horizon
            test_start = train_end + horizon
            if train_stop <= 0 or test_start >= test_end:
                continue

            X_train, y_train = X[:train_stop], y[:train_stop]
            X_test, y_test = X[test_start:test_end], y[test_start:test_end]

            model = RandomForestClassifier(
                n_estimators=n_estimators,
                max_depth=10,
                min_samples_split=10,
                min_samples_leaf=5,
                random_state=42,
                n_jobs=-1,
            )
            model.fit(X_train, y_train)
            acc = float(accuracy_score(y_test, model.predict(X_test)))

            folds.append({
                "fold": k,
                "train_size": len(X_train),
                "test_size": len(X_test),
                "accuracy": round(acc, 4),
            })

        if not folds:
            return None

        return {
            "code": code,
            "model_type": model_type,
            "horizon": horizon,
            "folds": folds,
            "mean_accuracy": round(sum(f["accuracy"] for f in folds) / len(folds), 4),
        }

    def train(
        self,
        code: str,
        count: int = 800,
        horizon: int = 5,
        threshold: float = 2.0,
        test_ratio: float = 0.2,
    ) -> Optional[dict]:
        """训练 ML 模型

        Args:
            code: 股票代码
            count: K线数量
            horizon: 预测未来天数
            threshold: 涨跌阈值(%)
            test_ratio: 测试集比例

        Returns:
            训练结果 dict (accuracy, classification_report, feature_importance 等)
        """
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.metrics import accuracy_score, classification_report

        try:
            import xgboost as xgb
            has_xgb = True
        except ImportError:
            has_xgb = False

        df = self._prepare_data(code, count, horizon, threshold)
        if df is None:
            return None

        feature_cols = self.feature_engine.get_feature_columns(df)
        X = df[feature_cols].values
        y = df["label"].values

        # 时序切分（不能随机！），切分点两侧留出 horizon 的间隔
        train_slice, test_slice = time_split_indices(len(X), test_ratio, gap=horizon)
        X_train, X_test = X[train_slice], X[test_slice]
        y_train, y_test = y[train_slice], y[test_slice]

        # 切分出来的训练窗口（用于报告"这个模型看过哪些数据"）
        holdout_start, holdout_end = self._window_dates(df, train_slice)
        # 评估完成后会在全量数据上重训，最终落盘的模型看到的是完整区间
        full_start, full_end = self._window_dates(df, slice(0, len(X)))
        expires_at = self._expiry_timestamp()

        window_meta = {
            "train_start": full_start,
            "train_end": full_end,
            "holdout_train_start": holdout_start,
            "holdout_train_end": holdout_end,
            # 准确率来自留出集，但模型本身在全量数据上重训过
            "fitted_on": "full",
            "expires_at": expires_at,
        }

        results = {}

        # ── RandomForest ──
        rf = RandomForestClassifier(
            n_estimators=200,
            max_depth=10,
            min_samples_split=10,
            min_samples_leaf=5,
            random_state=42,
            n_jobs=-1,
        )
        rf.fit(X_train, y_train)
        rf_pred = rf.predict(X_test)
        rf_acc = accuracy_score(y_test, rf_pred)
        rf_report = classification_report(y_test, rf_pred, target_names=["跌", "震荡", "涨"], zero_division=0, output_dict=True)
        rf_importance = dict(zip(feature_cols, rf.feature_importances_.tolist()))

        # 留出集评估完就在全量数据上重训：否则落盘模型会白白浪费最近 20% 的数据
        rf.fit(X, y)

        self.model_manager.save_ml_model(rf, code, "rf", meta={
            "accuracy": rf_acc,
            "horizon": horizon,
            "threshold": threshold,
            "features": feature_cols,
            "train_size": len(X),
            "test_size": len(X_test),
            **window_meta,
        })

        results["rf"] = {
            "accuracy": rf_acc,
            "report": rf_report,
            "feature_importance": rf_importance,
        }

        # ── XGBoost ──
        if has_xgb:
            # 标签映射: -1,0,1 → 0,1,2
            label_map = {-1: 0, 0: 1, 1: 2}
            y_train_xgb = np.array([label_map[v] for v in y_train])

            xgb_model = xgb.XGBClassifier(
                n_estimators=300,
                max_depth=6,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                reg_alpha=0.1,
                reg_lambda=1.0,
                random_state=42,
                eval_metric="mlogloss",
            )
            xgb_model.fit(X_train, y_train_xgb)
            xgb_pred_mapped = xgb_model.predict(X_test)
            # 映射回来
            inv_map = {0: -1, 1: 0, 2: 1}
            xgb_pred = np.array([inv_map[v] for v in xgb_pred_mapped])
            xgb_acc = accuracy_score(y_test, xgb_pred)
            xgb_report = classification_report(y_test, xgb_pred, target_names=["跌", "震荡", "涨"], zero_division=0, output_dict=True)
            xgb_importance = dict(zip(feature_cols, xgb_model.feature_importances_.tolist()))

            # 同 RF：留出集评估后在全量数据上重训
            xgb_model.fit(X, np.array([label_map[v] for v in y]))

            self.model_manager.save_ml_model(xgb_model, code, "xgb", meta={
                "accuracy": xgb_acc,
                "horizon": horizon,
                "threshold": threshold,
                "features": feature_cols,
                "label_map": label_map,
                "train_size": len(X),
                "test_size": len(X_test),
                **window_meta,
            })

            results["xgb"] = {
                "accuracy": xgb_acc,
                "report": xgb_report,
                "feature_importance": xgb_importance,
            }

        results["meta"] = {
            "code": code,
            "total_samples": len(X),
            "train_size": len(X_train),
            "test_size": len(X_test),
            "horizon": horizon,
            "threshold": threshold,
            "n_features": len(feature_cols),
            "label_distribution": {
                "涨": int((y == 1).sum()),
                "震荡": int((y == 0).sum()),
                "跌": int((y == -1).sum()),
            },
        }

        return results

    def predict(
        self,
        code: str,
        model_type: str = "xgb",
        auto_train: bool = False,
    ) -> Optional[dict]:
        """用已训练模型预测最新状态

        Args:
            code: 股票代码
            model_type: 使用的模型 (rf / xgb)
            auto_train: 缺模型时是否自动训练。默认 False —— 批量扫描时
                        隐式训练会让耗时从秒级变成分钟级，且结果不可控。

        Returns:
            预测结果 dict；缺模型且不允许自动训练时返回 None
        """
        # 加载模型
        payload = self.model_manager.load_ml_model(code, model_type)
        if payload is None:
            if not auto_train:
                logger.warning(
                    f"未找到 {code} 的 {model_type} 模型，请先执行 train-ai 训练；"
                    f"或在调用时显式指定 auto_train=True"
                )
                return None

            logger.info(f"未找到 {code} 的 {model_type} 模型，开始训练...")
            train_result = self.train(code)
            if train_result is None:
                return None
            payload = self.model_manager.load_ml_model(code, model_type)
            if payload is None:
                return None

        model = payload["model"]
        meta = payload["meta"]
        feature_cols = meta.get("features", [])

        # 获取最新数据
        df = self.market_service.get_kline_df(code, period="day", count=200, adjust="qfq")
        if df is None or len(df) < 70:
            return None

        df = self.feature_engine.build_features(df, dropna=True)
        if df.empty:
            return None

        # 取最后一行作为当前特征
        X_latest = df[feature_cols].iloc[[-1]].values

        # 预测
        if model_type == "xgb":
            label_map = meta.get("label_map", {-1: 0, 0: 1, 1: 2})
            inv_map = {v: k for k, v in label_map.items()}
            pred_mapped = model.predict(X_latest)[0]
            prediction = inv_map.get(pred_mapped, 0)
            proba_mapped = model.predict_proba(X_latest)[0]
            # 构建概率映射
            proba = {}
            for idx, label_val in inv_map.items():
                if idx < len(proba_mapped):
                    proba[label_val] = float(proba_mapped[idx])
        else:
            prediction = int(model.predict(X_latest)[0])
            proba_raw = model.predict_proba(X_latest)[0]
            classes = model.classes_
            proba = {int(c): float(p) for c, p in zip(classes, proba_raw)}

        signal_map = {1: "看涨", 0: "震荡", -1: "看跌"}
        confidence = proba.get(prediction, 0)

        # 获取 Top 特征因子
        if hasattr(model, "feature_importances_"):
            imp = model.feature_importances_
        else:
            imp = np.zeros(len(feature_cols))

        top_features = sorted(
            zip(feature_cols, imp),
            key=lambda x: x[1],
            reverse=True,
        )[:10]

        # 最新指标快照
        latest = df.iloc[-1]
        indicators = {}
        for col in ["rsi6", "rsi12", "macd_dif", "macd_dea", "macd_hist", "macd_cross",
                     "kdj_k", "kdj_d", "kdj_j", "boll_pct", "ma_bull", "vol_ratio",
                     "atr_pct", "return_1d", "return_5d", "bias5"]:
            if col in latest.index:
                indicators[col] = round(float(latest[col]), 2)

        return {
            "code": code,
            "model_type": model_type,
            "signal": signal_map.get(prediction, "未知"),
            "signal_value": prediction,
            "confidence": round(confidence * 100, 1),
            "probabilities": {signal_map.get(k, str(k)): round(v * 100, 1) for k, v in proba.items()},
            "top_features": [{"name": n, "importance": round(v, 4)} for n, v in top_features],
            "indicators": indicators,
            "model_accuracy": meta.get("accuracy", 0),
            "horizon": meta.get("horizon", 5),
            "threshold": meta.get("threshold", 2.0),
        }

    def batch_predict(self, codes: list, model_type: str = "xgb") -> list:
        """批量预测多只股票"""
        results = []
        for code in codes:
            try:
                result = self.predict(code, model_type)
                if result:
                    results.append(result)
            except Exception as e:
                logger.error(f"预测 {code} 失败: {e}")
        # 按置信度排序
        results.sort(key=lambda x: x.get("confidence", 0), reverse=True)
        return results
