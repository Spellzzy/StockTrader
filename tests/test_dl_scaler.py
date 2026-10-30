"""DL 数据预处理：标准化必须在切分之后只拟合训练集"""

import numpy as np

from app.ai.split import fit_scaler_on_train


def test_scaler_is_fitted_on_train_only():
    rng = np.random.default_rng(0)
    x_train = rng.normal(10.0, 2.0, size=(200, 4))
    x_test = rng.normal(50.0, 5.0, size=(50, 4))  # 分布明显不同

    x_train_scaled, x_test_scaled, scaler = fit_scaler_on_train(x_train, x_test)

    assert scaler.mean_.shape == (4,)
    assert np.allclose(x_train_scaled.mean(axis=0), 0.0, atol=1e-8)
    # 测试集用的是训练集的统计量，因此不会被自身分布归一化
    assert not np.allclose(x_test_scaled.mean(axis=0), 0.0, atol=1e-2)


def test_scaler_keeps_shape():
    x_train = np.arange(60, dtype=float).reshape(20, 3)
    x_test = np.arange(15, dtype=float).reshape(5, 3)

    x_train_scaled, x_test_scaled, _ = fit_scaler_on_train(x_train, x_test)
    assert x_train_scaled.shape == (20, 3)
    assert x_test_scaled.shape == (5, 3)
