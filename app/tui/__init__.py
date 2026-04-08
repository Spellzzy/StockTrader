"""TUI Dashboard — 基于 Textual 的全屏交互面板

架构分层:
    app/tui/
    ├── __init__.py          # 模块入口
    ├── app.py               # Textual App 主类
    ├── dashboard.tcss       # Textual CSS 布局样式
    ├── services.py          # ServiceContainer (服务容器，统一管理生命周期)
    ├── screens/
    │   └── main.py          # 主屏幕 (组装所有面板)
    └── widgets/
        ├── __init__.py      # Widget 统一导出
        ├── watchlist.py     # 自选股侧边栏
        ├── quote_panel.py   # 实时行情面板
        ├── alert_log.py     # 预警日志
        ├── portfolio.py     # 持仓概览 Tab
        ├── trades.py        # 交易记录 Tab
        ├── ai_panel.py      # AI 分析 Tab
        └── status_bar.py    # 底部状态栏/快捷键
"""
