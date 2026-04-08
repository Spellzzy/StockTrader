"""预测服务 — 统一入口，融合 ML + DL + LLM 分析

提供面向 CLI 的高层接口：
    - predict(code)     → 综合预测报告
    - analyze(code)     → LLM 深度分析报告
    - scan(codes)       → 批量扫描信号排名
    - train(code)       → 训练所有模型
"""

import logging
from typing import Optional

from app.ai.ml_predictor import MLPredictor
from app.ai.model_manager import ModelManager

logger = logging.getLogger(__name__)


class PredictorService:
    """AI 预测统一服务层"""

    def __init__(self):
        self.ml = MLPredictor()
        self.model_manager = ModelManager()
        self._dl = None  # 延迟加载 DL，避免无 torch 时报错

    @property
    def dl(self):
        """延迟加载 DL 预测器"""
        if self._dl is None:
            try:
                from app.ai.dl_predictor import DLPredictor
                self._dl = DLPredictor()
            except ImportError:
                self._dl = None
        return self._dl

    @property
    def has_dl(self) -> bool:
        """检查 PyTorch 是否可用"""
        try:
            import torch
            return True
        except ImportError:
            return False

    @property
    def llm(self):
        """延迟加载 LLM 分析器"""
        if not hasattr(self, '_llm') or self._llm is None:
            try:
                from app.ai.llm_analyzer import LLMAnalyzer
                self._llm = LLMAnalyzer()
            except ImportError:
                self._llm = None
        return self._llm

    @property
    def has_llm(self) -> bool:
        """检查 LLM 是否已配置"""
        return self.llm is not None and self.llm.is_configured

    # ==================== 训练 ====================

    def train(self, code: str, use_dl: bool = False) -> dict:
        """训练 ML（和可选的 DL）模型

        Args:
            code: 股票代码
            use_dl: 是否同时训练 DL 模型

        Returns:
            训练结果汇总
        """
        results = {}

        # ML 训练
        logger.info(f"开始训练 ML 模型: {code}")
        ml_result = self.ml.train(code)
        results["ml"] = ml_result

        # DL 训练
        if use_dl:
            if not self.has_dl:
                results["dl"] = {"error": "PyTorch 未安装，跳过 DL 训练"}
            else:
                logger.info(f"开始训练 DL-LSTM 模型: {code}")
                dl_result = self.dl.train(code, model_type="lstm")
                results["dl_lstm"] = dl_result

        return results

    # ==================== 预测 ====================

    def predict(self, code: str, use_dl: bool = False) -> Optional[dict]:
        """综合预测（融合 ML + DL）

        Returns:
            {
                "code": "sh600519",
                "ml": { ML 预测结果 },
                "dl": { DL 预测结果 } | None,
                "combined": { 融合后的综合结果 },
            }
        """
        result = {"code": code}

        # ML 预测 (XGBoost 优先)
        ml_xgb = self.ml.predict(code, model_type="xgb")
        ml_rf = self.ml.predict(code, model_type="rf")
        result["ml_xgb"] = ml_xgb
        result["ml_rf"] = ml_rf

        # DL 预测
        dl_result = None
        if use_dl and self.has_dl:
            try:
                dl_result = self.dl.predict(code, model_type="lstm")
            except Exception as e:
                logger.error(f"DL 预测失败: {e}")
        result["dl"] = dl_result

        # 融合结果
        result["combined"] = self._combine_predictions(ml_xgb, ml_rf, dl_result)

        return result

    def _combine_predictions(
        self,
        ml_xgb: Optional[dict],
        ml_rf: Optional[dict],
        dl_result: Optional[dict],
    ) -> dict:
        """融合多个模型的预测结果

        权重: XGBoost 0.4 + RandomForest 0.25 + DL 0.35
        如果缺少某个模型，重新分配权重。
        """
        signal_values = []  # (signal_value, confidence, weight)

        if ml_xgb:
            signal_values.append((ml_xgb["signal_value"], ml_xgb["confidence"], 0.4))
        if ml_rf:
            signal_values.append((ml_rf["signal_value"], ml_rf["confidence"], 0.25))
        if dl_result:
            signal_values.append((dl_result["signal_value"], dl_result["confidence"], 0.35))

        if not signal_values:
            return {"signal": "无数据", "score": 0, "confidence": 0}

        # 归一化权重
        total_weight = sum(w for _, _, w in signal_values)
        normalized = [(sv, conf, w / total_weight) for sv, conf, w in signal_values]

        # 加权评分 (-100 ~ +100)
        weighted_signal = sum(sv * conf * w for sv, conf, w in normalized)
        weighted_confidence = sum(conf * w for _, conf, w in normalized)

        # 判断综合信号
        if weighted_signal > 15:
            signal = "看涨"
            stars = min(5, int(weighted_signal / 15) + 1)
        elif weighted_signal < -15:
            signal = "看跌"
            stars = min(5, int(abs(weighted_signal) / 15) + 1)
        else:
            signal = "震荡"
            stars = max(1, 3 - int(abs(weighted_signal) / 10))

        # 收集关键因子
        key_factors = []
        if ml_xgb and "indicators" in ml_xgb:
            ind = ml_xgb["indicators"]
            # MACD 信号
            if ind.get("macd_cross") == 1:
                key_factors.append("✅ MACD 金叉")
            elif ind.get("macd_cross") == -1:
                key_factors.append("❌ MACD 死叉")

            # RSI
            rsi = ind.get("rsi6", 50)
            if rsi > 80:
                key_factors.append(f"⚠️ RSI={rsi} 超买区间")
            elif rsi < 20:
                key_factors.append(f"✅ RSI={rsi} 超卖区间")

            # 均线
            if ind.get("ma_bull") == 1:
                key_factors.append("✅ 均线多头排列")

            # 量比
            vol_ratio = ind.get("vol_ratio", 1)
            if vol_ratio > 2:
                key_factors.append(f"📊 量比={vol_ratio}，放量")

            # 布林
            boll = ind.get("boll_pct", 0.5)
            if boll > 0.9:
                key_factors.append("⚠️ 价格接近布林上轨")
            elif boll < 0.1:
                key_factors.append("✅ 价格接近布林下轨")

        return {
            "signal": signal,
            "score": round(weighted_signal, 1),
            "confidence": round(weighted_confidence, 1),
            "stars": stars,
            "key_factors": key_factors,
            "models_used": len(signal_values),
        }

    # ==================== LLM 分析 ====================

    def analyze(self, code: str, use_dl: bool = False) -> dict:
        """LLM 深度分析（Phase 3）

        先运行 ML/DL 预测，再用 LLM 综合多维数据生成分析报告。

        Args:
            code: 股票代码
            use_dl: 是否同时使用 DL 模型

        Returns:
            {
                "code": str,
                "prediction": { ML/DL 预测结果 },
                "report": AnalysisReport.to_dict(),
                "error": str | None,
            }
        """
        result = {"code": code, "prediction": None, "report": None, "error": None}

        # 1. 先跑 ML/DL 预测
        try:
            prediction = self.predict(code, use_dl=use_dl)
            result["prediction"] = prediction
        except Exception as e:
            logger.error(f"ML/DL 预测失败: {e}")
            prediction = None

        # 2. LLM 分析
        if self.llm is None:
            result["error"] = "LLM 模块不可用"
            return result

        if not self.llm.is_configured:
            from app.ai.llm_analyzer import LLMAnalyzer
            result["error"] = self.llm._get_config_hint()
            return result

        try:
            report = self.llm.analyze(code, prediction_result=prediction)
            if report.error:
                result["error"] = report.error
            result["report"] = report.to_dict()
        except Exception as e:
            logger.error(f"LLM 分析失败: {e}")
            result["error"] = f"LLM 分析失败: {e}"

        return result

    def analyze_batch(self, codes: list, use_dl: bool = False) -> list:
        """批量 LLM 分析多只股票

        Args:
            codes: 股票代码列表
            use_dl: 是否使用 DL

        Returns:
            分析结果列表，按 confidence 排序
        """
        results = []
        for code in codes:
            try:
                res = self.analyze(code, use_dl=use_dl)
                results.append(res)
            except Exception as e:
                logger.error(f"分析 {code} 失败: {e}")

        # 按 report.confidence 排序
        def get_confidence(r):
            report = r.get("report")
            if report:
                return report.get("confidence", 0)
            return 0

        results.sort(key=get_confidence, reverse=True)
        return results

    def test_llm(self) -> dict:
        """测试 LLM 连接"""
        if self.llm is None:
            return {"ok": False, "message": "LLM 模块不可用"}
        return self.llm.test_connection()

    # ==================== 批量扫描 ====================

    def scan(self, codes: list, use_dl: bool = False) -> list:
        """批量扫描多只股票，返回排名

        Returns:
            按综合评分排序的预测结果列表
        """
        results = []
        for code in codes:
            try:
                pred = self.predict(code, use_dl=use_dl)
                if pred and pred.get("combined"):
                    results.append(pred)
            except Exception as e:
                logger.error(f"扫描 {code} 失败: {e}")

        # 按综合评分排序
        results.sort(key=lambda x: x.get("combined", {}).get("score", 0), reverse=True)
        return results
