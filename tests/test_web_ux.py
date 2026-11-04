"""Web UX 增强层的静态一致性检查

这些能力都在前端（ux.js），用静态断言锁住控件、脚本顺序与关键实现，
避免再出现「接口通但页面不通」或增强层没被加载的情况。
"""

from fastapi.testclient import TestClient

import app.web.api as api_mod

client = TestClient(api_mod.app, raise_server_exceptions=False)


def test_ux_controls_present():
    html = client.get("/").text
    for marker in ("toast-box", "busy-bar", "busy-cancel", "cmd-panel",
                   "cmd-input", "cmd-open", "auto-refresh", "auto-interval",
                   "last-update"):
        assert marker in html, f"index.html 缺少 {marker}"


def test_script_order_enables_enhancement_layer():
    """ux.js 必须在 app.js 之后、p1/p2 之前，否则 p1/p2 解构不到增强版"""
    html = client.get("/").text
    order = [
        html.index("/static/app.js"),
        html.index("/static/ux.js"),
        html.index("/static/p1.js"),
        html.index("/static/p2.js"),
    ]
    assert order == sorted(order)
    assert client.get("/static/ux.js").status_code == 200


def test_ux_js_covers_all_four_areas():
    js = client.get("/static/ux.js").text
    # 加载反馈与缓存
    for marker in ("AbortController", "CACHE_PATHS", "ST.clearCache",
                   "setBusy", "showSkeleton", "function toast", "retry-btn"):
        assert marker in js, f"ux.js 缺少 {marker}"
    # 表格增强
    for marker in ("table-filter", "table-export", "table-pager",
                   "sortable", "exportCsv", "EMPTY_ACTIONS", "ST.tableRows ="):
        assert marker in js, f"ux.js 缺少 {marker}"
    # 通用代码选择器
    for marker in ("PICKER_IDS", "/api/code-picker", "attachCodePicker",
                   "picker-search", "picker-item"):
        assert marker in js, f"ux.js 缺少 {marker}"
    # 自动刷新与导航
    for marker in ("auto-refresh", "setInterval", "document.hidden",
                   "st.tab", "cmdFiltered", "ctrlKey"):
        assert marker in js, f"ux.js 缺少 {marker}"


def test_performance_enhancements_are_wired():
    app_js = client.get("/static/app.js").text
    ux_js = client.get("/static/ux.js").text
    # health 与页面数据并行，且 version 不再重复请求
    for marker in ("healthP", "loaderP", "window.ST.version"):
        assert marker in app_js, f"app.js 缺少 {marker}"
    assert "await api('/api/health')" not in app_js
    # GET 并发去重 + 手动刷新强制拉新
    for marker in ("inflight", "performRequest", "forceRefresh",
                   "/api/cache/clear-quotes"):
        assert marker in ux_js, f"ux.js 缺少 {marker}"


def test_picker_mount_deferred_until_dom_ready():
    """解析期搬动 input 会让宿主 WebView 的元素引用失效，必须等 DOM 就绪"""
    js = client.get("/static/ux.js").text
    assert "mountPickers" in js
    assert "document.readyState" in js
    assert "DOMContentLoaded" in js
    assert "PICKER_IDS.forEach(id => attachCodePicker($(id)))" in js


def test_code_picker_covers_all_code_inputs():
    js = client.get("/static/ux.js").text
    for input_id in ("wl-code", "codes", "kline-code", "bt-code", "lab-code",
                     "pos-code", "w-code", "a-code", "p-code"):
        assert f"'{input_id}'" in js, f"通用选择器未挂载 {input_id}"


def test_ux_styles_present():
    css = client.get("/static/style.css").text
    for cls in (".toast-box", ".busy-bar", ".table-tools", ".picker-pop",
                ".cmd-panel", ".skeleton-bar", ".empty-actions"):
        assert cls in css, f"style.css 缺少 {cls}"
