"""AI 模块（渐进式迭代）

Phase 1/2: ML/DL 预测模型
Phase 3:   LLM 分析总结

模块结构:
    feature_engine.py    — 技术指标特征工程
    ml_predictor.py      — ML 预测 (RandomForest + XGBoost)
    dl_predictor.py      — DL 预测 (LSTM + Transformer)
    model_manager.py     — 模型保存/加载/版本管理
    predictor_service.py — 统一入口(融合 ML+DL+LLM)
    prompt_builder.py    — Prompt 组装(多维数据→结构化提示词)
    llm_analyzer.py      — LLM 分析引擎(多后端支持)
"""

from app.ai.feature_engine import FeatureEngine
from app.ai.ml_predictor import MLPredictor
from app.ai.model_manager import ModelManager
from app.ai.predictor_service import PredictorService

__all__ = [
    "FeatureEngine",
    "MLPredictor",
    "ModelManager",
    "PredictorService",
]
