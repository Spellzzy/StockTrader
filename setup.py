from setuptools import setup, find_packages

setup(
    name="stock-trader-ai",
    version="0.1.0",
    description="AI辅助股票交易工具 - 记录、分析、复盘、预测",
    author="SpellZhu",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "typer>=0.9.0",
        "rich>=13.0.0",
        "sqlalchemy>=2.0.0",
        "pandas>=2.0.0",
        "numpy>=1.24.0",
        "matplotlib>=3.7.0",
        "plotly>=5.15.0",
        "pyyaml>=6.0",
        "python-dateutil>=2.8.0",
        "tabulate>=0.9.0",
        "scikit-learn>=1.3.0",
        "xgboost>=2.0.0",
        "joblib>=1.3.0",
    ],
    entry_points={
        "console_scripts": [
            "stock-ai=app.cli:app",
        ],
    },
)
