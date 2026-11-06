"""Web UX 增强层的静态一致性检查

这些能力都在前端（ux.js），用静态断言锁住控件、脚本顺序与关键实现，
避免再出现「接口通但页面不通」或增强层没被加载的情况。
"""

import os
import re

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
    assert "PICKER_IDS.forEach(id => attachCodePicker($(id), true))" in js
    assert "DETAIL_ONLY_IDS" in js and "'predict-code'" in js


def test_stock_codes_are_linkified_globally():
    """详情入口不能只绑在某一类表格上"""
    js = client.get("/static/ux.js").text
    assert "function linkifyCodes" in js
    assert "root.querySelectorAll('td')" in js
    assert "linkifyCodes(table)" in js          # tableRows 渲染的表
    assert "linkifyCodes()" in js               # refresh 后的全局扫描
    assert "td.cellIndex === 0" in js           # 纯 6 位数字仅第一列才认
    assert "td.classList.contains('num')" in js  # 数值列不误伤


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


def test_static_resources_are_not_cached():
    """预览 WebView 曾缓存旧 JS，导致改了代码页面仍是旧版"""
    page = client.get("/")
    assert page.status_code == 200
    assert "no-store" in page.headers.get("cache-control", "")
    assert not page.headers.get("etag")

    js = client.get("/static/p1.js?v=smoke")
    assert js.status_code == 200
    assert "no-store" in js.headers.get("cache-control", "")
    assert not js.headers.get("etag")


def test_index_injects_static_version():
    """任一静态文件内容变化都要让引用 URL 改变"""
    html = client.get("/").text
    matches = re.findall(
        r"/static/([\w.-]+\.(?:js|css))\?v=([0-9a-f]{12})", html
    )
    assert matches, "静态资源 URL 未注入版本号"
    names = [m[0] for m in matches]
    for name in ("app.js", "ux.js", "p1.js", "p2.js", "detail.js",
                 "scan.js", "style.css"):
        assert name in names, f"{name} 缺少版本号"
    assert len({m[1] for m in matches}) == 1  # 一次响应内版本一致


def test_layout_and_interaction_wiring():
    """布局偏好与操作手感的控件、逻辑、样式三者都要接线"""
    html = client.get("/").text
    for marker in ("density-compact", "to-top", "data-enter=", "data-gate=",
                   "side-nav", "w-amount", "pos-amount"):
        assert marker in html, f"index.html 缺少 {marker}"

    ux = client.get("/static/ux.js").text
    for marker in ("syncConfirmGates", "applyDensity", "scrollActiveTabIntoView",
                   "data-enter", "kbd-active", "syncToTop"):
        assert marker in ux, f"ux.js 缺少 {marker}"

    p2 = client.get("/static/p2.js").text
    assert "bindAmountPreview" in p2
    assert "syncConfirmGates" in p2

    css = client.get("/static/style.css").text
    for marker in ("density-compact", "position: sticky", "prefers-reduced-motion",
                   ":focus-visible", ".to-top", ".picker-item.kbd-active"):
        assert marker in css, f"style.css 缺少 {marker}"


def test_no_short_lived_dom_removal():
    """短生命周期节点被 remove 会让预览 WebView 注入脚本拿到 null 元素"""
    js = client.get("/static/ux.js").text
    assert "item.remove()" not in js
    assert "tr.remove()" not in js
    assert ".toast.free" in js            # toast 复用固定节点池
    assert "classList.add('hidden')" in js  # 骨架行只隐藏
    assert "items.dataset.built === '1'" in js  # picker 选项只构建一次
    assert "search.addEventListener('input', applyFilter)" in js


def test_cache_policy_and_training_invalidation():
    """训练轮询不能被当慢任务缓存；训练完成后必须失效预测缓存"""
    ux = client.get("/static/ux.js").text
    for marker in ("cacheHinted", "hasBusinessError", "ST.cachePolicy",
                   "ST.invalidate", "CACHE_PATHS"):
        assert marker in ux, f"ux.js 缺少 {marker}"

    p1 = client.get("/static/p1.js").text
    assert "ST.invalidate('/api/predict?')" in p1
    assert "await checkModelStatus();" in p1


NAV_GROUPS = {
    "daily": ["overview", "market", "analysis"],
    "analysis": ["backtest", "lab", "scan", "predict"],
    "trade": ["trades", "write", "alerts", "paper"],
    "system": ["settings", "reports"],
}


def _nav_group_html(html, group):
    match = re.search(
        rf'<section class="nav-group(?: has-active)?" data-group="{group}"[\s\S]*?</section>',
        html,
    )
    assert match, f"侧栏缺少分组 {group}"
    return match.group(0)


def test_sidebar_replaces_horizontal_tabs():
    """13 个横 tab 换成左侧四组导航，data-tab 与 panel id 保持不变"""
    html = client.get("/").text
    assert 'class="tabs"' not in html
    assert "tab-group-start" not in html
    assert 'id="side-nav"' in html
    assert 'id="side-toggle"' in html
    assert 'class="app-shell"' in html

    head, side, _rest = html.partition('id="side-nav"')
    for marker in ('class="brand"', 'id="status"', 'id="last-update"',
                   'id="auto-refresh"', 'id="density-compact"',
                   'id="refresh"', 'id="cmd-open"'):
        assert marker in head, f"顶栏缺少 {marker}"
        assert marker not in side.split("<main", 1)[0]

    ordered = []
    for group, tabs in NAV_GROUPS.items():
        block = _nav_group_html(html, group)
        found = re.findall(r'data-tab="([^"]+)"', block)
        assert found == tabs, f"{group} 的 data-tab 顺序应为 {tabs}，实际 {found}"
        toggle = re.search(r'<button[^>]*class="([^"]*)"[^>]*>', block)
        assert toggle and "nav-group-toggle" in toggle.group(1)
        assert "tab" not in toggle.group(1).split()
        ordered.extend(tabs)
    assert ordered == re.findall(r'data-tab="([^"]+)"', html)
    for tab in ordered:
        assert html.count(f'data-tab="{tab}"') == 1
        assert f'id="panel-{tab}"' in html
    assert 'data-tab="overview"' in html and 'aria-current="page"' in html
    assert 'class="tab active"' in html


def test_sidebar_state_is_separate_from_density():
    """组折叠与侧栏展开写入自己的 localStorage；紧凑密度仍只作用于主区"""
    ux = client.get("/static/ux.js").text
    for marker in ("st.side", "st.nav.groups", "ST.nav", "setGroupCollapsed",
                   "959px", "side-toggle", "scrollActiveTabIntoView", "goTab"):
        assert marker in ux, f"ux.js 缺少 {marker}"
    assert "st.density" in ux

    app_js = client.get("/static/app.js").text
    assert "dataset.tab" in app_js
    assert "'panel-' +" in app_js or '"panel-" +' in app_js
    assert "aria-current" in app_js

    css = client.get("/static/style.css").text
    for marker in (".side-nav", "side-rail", "side-expanded", "959px",
                   ".nav-group.is-collapsed", ".tab.active"):
        assert marker in css, f"style.css 缺少 {marker}"
    assert ".tabs {" not in css
    assert "tab-group-start" not in css
    assert "density-compact .tab" not in css


def test_sidebar_column_reaches_bottom_of_shell():
    """短页侧栏要撑满顶栏以下的整列，脚注沉底；高页仍靠 sticky 与 max-height 内滚。"""
    css = client.get("/static/style.css").text

    body = re.search(r"body\s*\{([^}]*)\}", css)
    assert body, "缺少 body 规则"
    body_decl = body.group(1)
    assert "display: flex" in body_decl
    assert "flex-direction: column" in body_decl
    assert "min-height: 100vh" in body_decl

    shell = re.search(r"\.app-shell\s*\{([^}]*)\}", css)
    assert shell, "缺少 .app-shell"
    assert "flex: 1 0 auto" in shell.group(1)
    assert "align-items: flex-start" in shell.group(1)

    side = re.search(r"\.side-nav\s*\{([^}]*)\}", css)
    assert side, "缺少 .side-nav"
    side_decl = side.group(1)
    assert "align-self: stretch" in side_decl
    assert "align-self: flex-start" not in side_decl
    assert "position: sticky" in side_decl
    assert "max-height: 100vh" in side_decl
    assert "overflow-y: auto" in side_decl

    note = re.search(r"\.tabs-note\s*\{([^}]*)\}", css)
    assert note, "缺少 .tabs-note"
    assert "margin-top: auto" in note.group(1)


def test_static_version_changes_with_file(monkeypatch, tmp_path):
    path = tmp_path / "app.js"
    path.write_text("old", encoding="utf-8")
    monkeypatch.setattr(api_mod, "STATIC_DIR", tmp_path)
    v1 = api_mod._static_version()

    path.write_text("new content", encoding="utf-8")
    os.utime(path, ns=(path.stat().st_atime_ns,
                       path.stat().st_mtime_ns + 1_000_000_000))
    assert api_mod._static_version() != v1
