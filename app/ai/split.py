"""时序数据的切分与标准化工具

为什么需要 gap:
    分类标签是用「未来 horizon 天的收益」构造的，所以第 i 条样本的标签
    实际上用到了第 i+horizon 天的价格。如果训练集和测试集紧邻切分：
    - 训练集末尾 horizon 条样本的标签区间会伸进测试集（信息泄漏）
    - 测试集开头同样与训练集尾部相邻
    因此切分点两侧都要留 horizon 的间隔（purge + embargo）。

为什么标准化要放在切分之后:
    StandardScaler 如果在全量数据上 fit，测试集的均值和方差就进入了训练过程，
    让评估指标虚高。必须只在训练集上 fit，再用它 transform 测试集。
"""

from typing import Tuple

from sklearn.preprocessing import StandardScaler


def time_split_indices(n: int, test_ratio: float = 0.2, gap: int = 0) -> Tuple[slice, slice]:
    """按时间顺序切分索引

    Args:
        n: 样本总数
        test_ratio: 测试集比例
        gap: 切分点两侧各丢弃的样本数（通常取标签 horizon）

    Returns:
        (train_slice, test_slice) —— 两个切片保证不重叠
    """
    split_idx = int(n * (1 - test_ratio))
    train_stop = split_idx
    test_start = split_idx

    if gap > 0:
        train_stop = split_idx - gap
        test_start = split_idx + gap
        # 数据量不足以留出间隔时退化为无间隔切分，而不是抛异常
        if train_stop < 1 or test_start >= n:
            train_stop = split_idx
            test_start = split_idx

    return slice(0, max(train_stop, 0)), slice(test_start, n)


def fit_scaler_on_train(x_train, x_test):
    """只在训练集上拟合标准化，再变换训练集和测试集

    Returns:
        (x_train_scaled, x_test_scaled, scaler)
    """
    scaler = StandardScaler()
    x_train_scaled = scaler.fit_transform(x_train)
    x_test_scaled = scaler.transform(x_test)
    return x_train_scaled, x_test_scaled, scaler
