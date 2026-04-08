"""DL 预测器 — 基于 PyTorch 深度学习的股票走势预测

支持 LSTM 和 Transformer 两种架构，捕捉时序模式。
可输出未来 N 日价格走势预测曲线。

用法:
    predictor = DLPredictor()
    result = predictor.train_and_predict("sh600519")
"""

import logging
from typing import Optional, Tuple

import numpy as np
import pandas as pd

from app.ai.feature_engine import FeatureEngine
from app.ai.model_manager import ModelManager
from app.services.market_service import MarketService

logger = logging.getLogger(__name__)

# ==================== PyTorch 模型定义 ====================

_TORCH_AVAILABLE = False
try:
    import torch
    import torch.nn as nn
    from torch.utils.data import Dataset, DataLoader
    _TORCH_AVAILABLE = True
except ImportError:
    pass


def _check_torch():
    if not _TORCH_AVAILABLE:
        raise ImportError(
            "PyTorch 未安装。请执行: pip install torch\n"
            "或访问 https://pytorch.org 选择适合的版本。"
        )


# ── Dataset ──

if _TORCH_AVAILABLE:
    class StockSequenceDataset(Dataset):
        """滑动窗口时序数据集"""

        def __init__(self, X: np.ndarray, y: np.ndarray, seq_len: int = 30):
            self.seq_len = seq_len
            self.X = torch.FloatTensor(X)
            self.y = torch.LongTensor(y)

        def __len__(self):
            return len(self.X) - self.seq_len + 1

        def __getitem__(self, idx):
            x_seq = self.X[idx: idx + self.seq_len]
            y_label = self.y[idx + self.seq_len - 1]
            return x_seq, y_label

    # ── LSTM 模型 ──

    class LSTMModel(nn.Module):
        """双层 LSTM + Attention 分类模型"""

        def __init__(self, input_dim: int, hidden_dim: int = 128, num_layers: int = 2,
                     num_classes: int = 3, dropout: float = 0.3):
            super().__init__()
            self.hidden_dim = hidden_dim
            self.num_layers = num_layers

            self.lstm = nn.LSTM(
                input_dim, hidden_dim, num_layers,
                batch_first=True, dropout=dropout, bidirectional=False,
            )
            self.attention = nn.Sequential(
                nn.Linear(hidden_dim, hidden_dim // 2),
                nn.Tanh(),
                nn.Linear(hidden_dim // 2, 1),
            )
            self.classifier = nn.Sequential(
                nn.LayerNorm(hidden_dim),
                nn.Linear(hidden_dim, 64),
                nn.ReLU(),
                nn.Dropout(dropout),
                nn.Linear(64, num_classes),
            )

        def forward(self, x):
            # x: (batch, seq_len, input_dim)
            lstm_out, _ = self.lstm(x)  # (batch, seq_len, hidden)

            # Attention
            attn_weights = self.attention(lstm_out)        # (batch, seq_len, 1)
            attn_weights = torch.softmax(attn_weights, dim=1)
            context = (lstm_out * attn_weights).sum(dim=1)  # (batch, hidden)

            out = self.classifier(context)
            return out

    # ── Transformer 模型 ──

    class TransformerModel(nn.Module):
        """Transformer Encoder 分类模型"""

        def __init__(self, input_dim: int, d_model: int = 128, nhead: int = 4,
                     num_layers: int = 2, num_classes: int = 3, dropout: float = 0.3,
                     max_seq_len: int = 60):
            super().__init__()
            self.d_model = d_model

            self.input_proj = nn.Linear(input_dim, d_model)
            self.pos_encoding = nn.Parameter(torch.randn(1, max_seq_len, d_model) * 0.02)

            encoder_layer = nn.TransformerEncoderLayer(
                d_model=d_model, nhead=nhead,
                dim_feedforward=d_model * 4, dropout=dropout,
                batch_first=True,
            )
            self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)

            self.classifier = nn.Sequential(
                nn.LayerNorm(d_model),
                nn.Linear(d_model, 64),
                nn.ReLU(),
                nn.Dropout(dropout),
                nn.Linear(64, num_classes),
            )

        def forward(self, x):
            # x: (batch, seq_len, input_dim)
            seq_len = x.size(1)
            x = self.input_proj(x) + self.pos_encoding[:, :seq_len, :]
            x = self.encoder(x)
            # 取最后一个时间步
            out = self.classifier(x[:, -1, :])
            return out


class DLPredictor:
    """深度学习预测器 (LSTM / Transformer)"""

    def __init__(self):
        self.feature_engine = FeatureEngine()
        self.model_manager = ModelManager()
        self.market_service = MarketService()

    def _prepare_data(
        self,
        code: str,
        count: int = 1000,
        horizon: int = 5,
        threshold: float = 2.0,
    ) -> Optional[Tuple[np.ndarray, np.ndarray, list]]:
        """获取并预处理数据

        Returns:
            (X_scaled, y, feature_cols) 或 None
        """
        from sklearn.preprocessing import StandardScaler

        df = self.market_service.get_kline_df(code, period="day", count=count, adjust="qfq")
        if df is None or len(df) < 150:
            logger.warning(f"数据不足: {code}")
            return None

        df = self.feature_engine.build_features(df, dropna=True)
        df = self.feature_engine.add_label_classification(df, horizon=horizon, threshold=threshold)

        if len(df) < 120:
            logger.warning(f"处理后数据不足: {code}, 仅 {len(df)} 条")
            return None

        feature_cols = self.feature_engine.get_feature_columns(df)
        X = df[feature_cols].values
        y = df["label"].values

        # 标准化
        scaler = StandardScaler()
        X = scaler.fit_transform(X)

        # 标签映射: -1,0,1 → 0,1,2
        label_map = {-1: 0, 0: 1, 1: 2}
        y = np.array([label_map[v] for v in y])

        return X, y, feature_cols, scaler

    def train(
        self,
        code: str,
        model_type: str = "lstm",
        count: int = 1000,
        horizon: int = 5,
        threshold: float = 2.0,
        seq_len: int = 30,
        epochs: int = 50,
        batch_size: int = 32,
        lr: float = 1e-3,
    ) -> Optional[dict]:
        """训练 DL 模型

        Args:
            code: 股票代码
            model_type: 模型类型 (lstm / transformer)
            count: K线数量
            horizon: 预测天数
            threshold: 涨跌阈值(%)
            seq_len: 序列长度(滑动窗口)
            epochs: 训练轮数
            batch_size: 批大小
            lr: 学习率

        Returns:
            训练结果
        """
        _check_torch()
        from sklearn.metrics import accuracy_score, classification_report

        result = self._prepare_data(code, count, horizon, threshold)
        if result is None:
            return None

        X, y, feature_cols, scaler = result
        input_dim = X.shape[1]

        # 时序切分
        split_idx = int(len(X) * 0.8)
        X_train, X_test = X[:split_idx], X[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]

        train_ds = StockSequenceDataset(X_train, y_train, seq_len)
        test_ds = StockSequenceDataset(X_test, y_test, seq_len)

        if len(train_ds) < 10 or len(test_ds) < 5:
            logger.warning(f"序列数据集太小: train={len(train_ds)}, test={len(test_ds)}")
            return None

        train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=False)
        test_loader = DataLoader(test_ds, batch_size=batch_size, shuffle=False)

        # 构建模型
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        if model_type == "transformer":
            model = TransformerModel(
                input_dim=input_dim, d_model=128, nhead=4,
                num_layers=2, num_classes=3, dropout=0.3,
                max_seq_len=seq_len,
            ).to(device)
        else:
            model = LSTMModel(
                input_dim=input_dim, hidden_dim=128, num_layers=2,
                num_classes=3, dropout=0.3,
            ).to(device)

        # 类别权重（处理不平衡）
        class_counts = np.bincount(y_train, minlength=3).astype(float) + 1
        class_weights = 1.0 / class_counts
        class_weights = class_weights / class_weights.sum() * 3
        weights_tensor = torch.FloatTensor(class_weights).to(device)

        criterion = nn.CrossEntropyLoss(weight=weights_tensor)
        optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

        # 训练
        best_acc = 0
        train_losses = []

        for epoch in range(epochs):
            model.train()
            epoch_loss = 0
            for X_batch, y_batch in train_loader:
                X_batch, y_batch = X_batch.to(device), y_batch.to(device)
                optimizer.zero_grad()
                output = model(X_batch)
                loss = criterion(output, y_batch)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
                optimizer.step()
                epoch_loss += loss.item()

            scheduler.step()
            avg_loss = epoch_loss / len(train_loader)
            train_losses.append(avg_loss)

            # 每 10 轮评估
            if (epoch + 1) % 10 == 0:
                model.eval()
                all_preds = []
                all_labels = []
                with torch.no_grad():
                    for X_batch, y_batch in test_loader:
                        X_batch = X_batch.to(device)
                        output = model(X_batch)
                        preds = output.argmax(dim=1).cpu().numpy()
                        all_preds.extend(preds)
                        all_labels.extend(y_batch.numpy())

                acc = accuracy_score(all_labels, all_preds)
                logger.info(f"Epoch {epoch+1}/{epochs} - loss: {avg_loss:.4f} - test_acc: {acc:.4f}")
                if acc > best_acc:
                    best_acc = acc

        # 最终评估
        model.eval()
        all_preds = []
        all_labels = []
        all_probs = []
        with torch.no_grad():
            for X_batch, y_batch in test_loader:
                X_batch = X_batch.to(device)
                output = model(X_batch)
                probs = torch.softmax(output, dim=1).cpu().numpy()
                preds = output.argmax(dim=1).cpu().numpy()
                all_preds.extend(preds)
                all_labels.extend(y_batch.numpy())
                all_probs.extend(probs)

        final_acc = accuracy_score(all_labels, all_preds)
        report = classification_report(
            all_labels, all_preds,
            target_names=["跌", "震荡", "涨"],
            zero_division=0, output_dict=True,
        )

        # 保存模型
        import joblib
        scaler_path = self.model_manager.dl_dir / f"{code}_{model_type}_scaler.joblib"
        joblib.dump({
            "scaler": scaler,
            "feature_cols": feature_cols,
            "seq_len": seq_len,
        }, scaler_path)

        self.model_manager.save_dl_model(model, code, model_type, meta={
            "accuracy": final_acc,
            "horizon": horizon,
            "threshold": threshold,
            "seq_len": seq_len,
            "input_dim": input_dim,
            "features": feature_cols,
            "model_arch": model_type,
            "epochs": epochs,
            "train_size": len(X_train),
            "test_size": len(X_test),
        })

        return {
            "model_type": model_type,
            "accuracy": final_acc,
            "report": report,
            "train_losses": train_losses[-10:],  # 只保留最后 10 轮
            "meta": {
                "code": code,
                "total_samples": len(X),
                "train_size": len(X_train),
                "test_size": len(X_test),
                "seq_len": seq_len,
                "epochs": epochs,
                "horizon": horizon,
                "threshold": threshold,
                "device": str(device),
            },
        }

    def predict(self, code: str, model_type: str = "lstm") -> Optional[dict]:
        """用已训练的 DL 模型预测

        Returns:
            预测结果 dict
        """
        _check_torch()
        import joblib

        # 加载模型
        payload = self.model_manager.load_dl_model(code, model_type)
        if payload is None:
            logger.warning(f"未找到 {code} 的 {model_type} 模型，将自动训练...")
            train_result = self.train(code, model_type=model_type)
            if train_result is None:
                return None
            payload = self.model_manager.load_dl_model(code, model_type)
            if payload is None:
                return None

        meta = payload["meta"]
        seq_len = meta.get("seq_len", 30)
        input_dim = meta.get("input_dim")
        feature_cols = meta.get("features", [])

        # 加载 scaler
        scaler_path = self.model_manager.dl_dir / f"{code}_{model_type}_scaler.joblib"
        if not scaler_path.exists():
            logger.warning("Scaler 文件不存在，需要重新训练")
            return None
        scaler_data = joblib.load(scaler_path)
        scaler = scaler_data["scaler"]

        # 获取最新数据
        df = self.market_service.get_kline_df(code, period="day", count=200, adjust="qfq")
        if df is None or len(df) < seq_len + 60:
            return None

        df = self.feature_engine.build_features(df, dropna=True)
        if len(df) < seq_len:
            return None

        X = df[feature_cols].values
        X = scaler.transform(X)

        # 取最后 seq_len 个时间步
        X_seq = torch.FloatTensor(X[-seq_len:]).unsqueeze(0)  # (1, seq_len, input_dim)

        # 重建模型
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        if model_type == "transformer":
            model = TransformerModel(
                input_dim=input_dim, d_model=128, nhead=4,
                num_layers=2, num_classes=3, dropout=0.3,
                max_seq_len=seq_len,
            )
        else:
            model = LSTMModel(
                input_dim=input_dim, hidden_dim=128, num_layers=2,
                num_classes=3, dropout=0.3,
            )

        model.load_state_dict(payload["model_state_dict"])
        model.to(device)
        model.eval()

        with torch.no_grad():
            X_seq = X_seq.to(device)
            output = model(X_seq)
            probs = torch.softmax(output, dim=1).cpu().numpy()[0]
            pred = output.argmax(dim=1).cpu().item()

        # 映射回来: 0→跌, 1→震荡, 2→涨
        inv_map = {0: -1, 1: 0, 2: 1}
        prediction = inv_map.get(pred, 0)
        signal_map = {1: "看涨", 0: "震荡", -1: "看跌"}

        return {
            "code": code,
            "model_type": model_type,
            "signal": signal_map.get(prediction, "未知"),
            "signal_value": prediction,
            "confidence": round(float(probs[pred]) * 100, 1),
            "probabilities": {
                "看跌": round(float(probs[0]) * 100, 1),
                "震荡": round(float(probs[1]) * 100, 1),
                "看涨": round(float(probs[2]) * 100, 1),
            },
            "model_accuracy": meta.get("accuracy", 0),
            "horizon": meta.get("horizon", 5),
            "threshold": meta.get("threshold", 2.0),
        }
