"""搜索弹窗 — 按 / 键弹出，支持搜索股票并添加到自选

功能:
    1. Input 输入框 + 实时搜索
    2. 搜索结果列表（代码 + 名称 + 市场）
    3. 回车添加到自选 / ESC 关闭
"""

from __future__ import annotations

import re
from typing import Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Input, Static, ListView, ListItem, Label
from textual.binding import Binding

from rich.text import Text


class SearchDialog(ModalScreen[Optional[str]]):
    """搜索股票弹窗

    返回:
        选中的股票代码(str) 或 None(取消)
    """

    BINDINGS = [
        Binding("escape", "cancel", "关闭", show=True),
    ]

    CSS = """
    SearchDialog {
        align: center middle;
    }

    #search-container {
        width: 64;
        max-width: 80;
        height: auto;
        max-height: 28;
        background: $surface;
        border: round $primary;
        padding: 1 2;
    }

    #search-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        width: 100%;
        height: 1;
        margin-bottom: 1;
    }

    #search-input {
        width: 100%;
        margin-bottom: 1;
    }

    #search-hint {
        height: 1;
        color: $text-muted;
        text-align: center;
        margin-bottom: 1;
    }

    #search-results {
        height: auto;
        max-height: 16;
        width: 100%;
    }

    #search-results ListItem {
        height: 2;
        padding: 0 1;
    }

    #search-results ListItem:hover {
        background: $surface-lighten-1;
    }

    #search-status {
        height: 1;
        color: $text-muted;
        text-align: center;
        margin-top: 1;
    }
    """

    class StockAdded(Message):
        """股票已添加到自选"""
        def __init__(self, stock_code: str, stock_name: str) -> None:
            super().__init__()
            self.stock_code = stock_code
            self.stock_name = stock_name

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._results: list[dict] = []
        self._search_timer = None

    def compose(self) -> ComposeResult:
        with Vertical(id="search-container"):
            yield Static("🔍 搜索股票", id="search-title")
            yield Input(
                placeholder="输入代码/名称/拼音首字母 (如: 600519, 贵州茅台, gzmt)",
                id="search-input",
            )
            yield Static("[Enter] 添加自选  [Esc] 关闭", id="search-hint")
            yield ListView(id="search-results")
            yield Static("", id="search-status")

    def on_mount(self) -> None:
        """聚焦到搜索框"""
        self.query_one("#search-input", Input).focus()

    @on(Input.Changed, "#search-input")
    def on_search_input_changed(self, event: Input.Changed) -> None:
        """搜索框内容变化 — 防抖搜索"""
        keyword = event.value.strip()
        if len(keyword) < 1:
            self._clear_results()
            return

        # 取消前一个定时器，实现防抖
        if self._search_timer:
            self._search_timer.stop()
        self._search_timer = self.set_timer(0.4, lambda: self._do_search(keyword))

    async def _do_search(self, keyword: str) -> None:
        """执行搜索"""
        status = self.query_one("#search-status", Static)
        status.update("搜索中...")

        try:
            services = self.app.services
            raw_text = await services.run_sync(services.market.search, keyword)
            self._results = self._parse_search_results(raw_text)
            self._render_results()
        except Exception as e:
            status.update(f"[red]搜索失败: {e}[/red]")
            self._results = []

    def _parse_search_results(self, raw_text: str) -> list[dict]:
        """解析搜索结果原始文本

        stock-data search 的输出格式可能是:
          代码        名称          市场
          sh600519    贵州茅台      上海A股
          sz000001    平安银行      深圳A股
        或者包含 [HTTP Request] 头部的多行文本
        """
        results = []
        if not raw_text:
            return results

        lines = raw_text.strip().splitlines()

        for line in lines:
            line = line.strip()
            # 跳过空行、HTTP 调试行、表头分隔线
            if not line or line.startswith("[HTTP") or line.startswith("---") or line.startswith("代码"):
                continue

            # 尝试匹配：代码 + 名称 + 其他
            # 匹配模式: (sh|sz|hk|us)\d+ 开头
            match = re.match(
                r'^((?:sh|sz|hk|us)\w+)\s+(.+?)(?:\s{2,}(.*))?$',
                line,
                re.IGNORECASE,
            )
            if match:
                code = match.group(1).strip().lower()
                name = match.group(2).strip()
                market_info = (match.group(3) or "").strip()
                results.append({
                    "code": code,
                    "name": name,
                    "market_info": market_info,
                })
                continue

            # 备选匹配：用空白分割
            parts = line.split()
            if len(parts) >= 2:
                code_candidate = parts[0].lower()
                # 判断是否像股票代码
                if re.match(r'^(sh|sz|hk|us)\d+', code_candidate):
                    results.append({
                        "code": code_candidate,
                        "name": parts[1],
                        "market_info": " ".join(parts[2:]) if len(parts) > 2 else "",
                    })

        return results[:20]  # 最多展示 20 条

    def _render_results(self) -> None:
        """渲染搜索结果"""
        listview = self.query_one("#search-results", ListView)
        status = self.query_one("#search-status", Static)
        listview.clear()

        if not self._results:
            status.update("[dim]未找到匹配的股票[/dim]")
            return

        for item in self._results:
            code = item["code"]
            name = item["name"]
            market_info = item.get("market_info", "")

            line1 = Text()
            line1.append(f"{code:<12s}", style="bold cyan")
            line1.append(f"{name}", style="bold")
            if market_info:
                line1.append(f"  {market_info}", style="dim")

            line2 = Text()
            line2.append("  ⏎ Enter 添加到自选", style="dim italic")

            list_item = ListItem(
                Label(line1),
                Label(line2),
                name=code,
            )
            listview.append(list_item)

        status.update(f"找到 {len(self._results)} 个结果")

    def _clear_results(self) -> None:
        """清空结果"""
        listview = self.query_one("#search-results", ListView)
        listview.clear()
        self._results = []
        self.query_one("#search-status", Static).update("")

    @on(ListView.Selected, "#search-results")
    def on_result_selected(self, event: ListView.Selected) -> None:
        """选中搜索结果 — 添加到自选"""
        item = event.item
        if not item.name:
            return

        code = item.name
        # 从结果中获取名称
        stock_info = next((r for r in self._results if r["code"] == code), None)
        name = stock_info["name"] if stock_info else code

        status = self.query_one("#search-status", Static)
        status.update(f"正在添加 {name}({code}) 到自选...")

        # 在后台异步执行添加操作
        self.run_worker(
            self._add_stock_to_watchlist(code, name),
            name="add_stock_worker",
        )

    async def _add_stock_to_watchlist(self, code: str, name: str) -> None:
        """异步添加股票到自选

        注意: 不在此处调用 self.dismiss()，因为 Textual 不允许
        从 screen 的消息处理链中调用 dismiss。
        关闭弹窗由 MainScreen 在收到 StockAdded 消息后通过 app.pop_screen() 完成。
        """
        status = self.query_one("#search-status", Static)
        try:
            services = self.app.services
            await services.run_sync(services.watchlist.add_watch, code)
            status.update(f"[green]✓ 已添加 {name}({code}) 到自选[/green]")
            # 发送消息通知 MainScreen 刷新并关闭弹窗
            self.post_message(self.StockAdded(stock_code=code, stock_name=name))
        except Exception as e:
            status.update(f"[red]添加失败: {e}[/red]")

    @on(Input.Submitted, "#search-input")
    def on_search_submitted(self, event: Input.Submitted) -> None:
        """在搜索框按回车 — 如果有结果就选中第一个"""
        listview = self.query_one("#search-results", ListView)
        if listview.children:
            # 模拟选中第一个
            first_item = listview.children[0]
            if hasattr(first_item, 'name') and first_item.name:
                listview.index = 0
                listview.action_select_cursor()

    def action_cancel(self) -> None:
        """ESC 关闭"""
        self.dismiss(None)
