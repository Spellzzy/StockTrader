"""模型管理器 — 模型的保存、加载与版本管理

模型存储结构:
    data/models/
    ├── ml/
    │   ├── sh600519_rf_20260408.joblib
    │   └── sh600519_xgb_20260408.joblib
    └── dl/
        └── sh600519_lstm_20260408.pt
"""

import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Any

from app.config import load_config

logger = logging.getLogger(__name__)


class ModelManager:
    """模型保存 / 加载 / 版本管理"""

    def __init__(self, base_dir: Optional[str] = None):
        if base_dir:
            self.base_dir = Path(base_dir)
        else:
            cfg = load_config()
            self.base_dir = Path(cfg.get("ai", {}).get("model", {}).get("save_dir", "./data/models"))

        self.ml_dir = self.base_dir / "ml"
        self.dl_dir = self.base_dir / "dl"
        self.ml_dir.mkdir(parents=True, exist_ok=True)
        self.dl_dir.mkdir(parents=True, exist_ok=True)

    # ==================== ML 模型 ====================

    def save_ml_model(self, model: Any, code: str, model_type: str = "xgb", meta: Optional[dict] = None):
        """保存 ML 模型

        Args:
            model: sklearn / xgboost 模型对象
            code: 股票代码
            model_type: 模型类型 (rf / xgb / lr)
            meta: 元信息 (accuracy, features 等)
        """
        import joblib

        date_str = datetime.now().strftime("%Y%m%d")
        filename = f"{code}_{model_type}_{date_str}.joblib"
        path = self.ml_dir / filename

        payload = {
            "model": model,
            "code": code,
            "model_type": model_type,
            "created_at": datetime.now().isoformat(),
            "meta": meta or {},
        }

        joblib.dump(payload, path)
        logger.info(f"ML 模型已保存: {path}")
        return str(path)

    def load_ml_model(self, code: str, model_type: str = "xgb") -> Optional[dict]:
        """加载最新的 ML 模型

        Returns:
            包含 model, code, meta 等键的 dict，找不到则返回 None
        """
        import joblib

        # 找到最新的匹配文件
        pattern = f"{code}_{model_type}_"
        candidates = sorted(
            [f for f in self.ml_dir.iterdir() if f.name.startswith(pattern) and f.suffix == ".joblib"],
            key=lambda f: f.name,
            reverse=True,
        )
        if not candidates:
            return None

        path = candidates[0]
        logger.info(f"加载 ML 模型: {path}")
        return joblib.load(path)

    # ==================== DL 模型 ====================

    def save_dl_model(self, model: Any, code: str, model_type: str = "lstm", meta: Optional[dict] = None):
        """保存 DL 模型 (PyTorch)"""
        import torch

        date_str = datetime.now().strftime("%Y%m%d")
        filename = f"{code}_{model_type}_{date_str}.pt"
        path = self.dl_dir / filename

        payload = {
            "model_state_dict": model.state_dict(),
            "code": code,
            "model_type": model_type,
            "created_at": datetime.now().isoformat(),
            "meta": meta or {},
        }

        torch.save(payload, path)
        logger.info(f"DL 模型已保存: {path}")
        return str(path)

    def load_dl_model(self, code: str, model_type: str = "lstm") -> Optional[dict]:
        """加载最新的 DL 模型"""
        import torch

        pattern = f"{code}_{model_type}_"
        candidates = sorted(
            [f for f in self.dl_dir.iterdir() if f.name.startswith(pattern) and f.suffix == ".pt"],
            key=lambda f: f.name,
            reverse=True,
        )
        if not candidates:
            return None

        path = candidates[0]
        logger.info(f"加载 DL 模型: {path}")
        return torch.load(path, map_location="cpu", weights_only=False)

    # ==================== 清理 ====================

    def list_models(self, code: Optional[str] = None) -> list:
        """列出所有已保存的模型"""
        models = []
        for d, kind in [(self.ml_dir, "ML"), (self.dl_dir, "DL")]:
            for f in sorted(d.iterdir()):
                if code and not f.name.startswith(code):
                    continue
                models.append({
                    "kind": kind,
                    "file": f.name,
                    "size_kb": f.stat().st_size / 1024,
                    "path": str(f),
                })
        return models

    def clean_old_models(self, code: str, keep: int = 3):
        """清理旧版本模型，每种类型只保留最新 keep 个"""
        for d in [self.ml_dir, self.dl_dir]:
            files = sorted(
                [f for f in d.iterdir() if f.name.startswith(code)],
                key=lambda f: f.name,
                reverse=True,
            )
            for f in files[keep:]:
                f.unlink()
                logger.info(f"清理旧模型: {f}")
