"""前端 JS 冒烟测试：三个脚本在同一全局环境依序执行不得抛错

回归背景：app.js 的 $ 是 getElementById，而 p1/p2 按 jQuery 风格传 '#id'，
导致 getElementById('#x') 返回 null、脚本顶层绑定事件时抛 TypeError，
整个 P1/P2 页面在真实浏览器中静默失效 —— 接口测试无法发现这类问题。
"""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "js_smoke.mjs"

node = shutil.which("node")
pytestmark = pytest.mark.skipif(node is None, reason="未安装 node，跳过 JS 冒烟测试")


def test_all_scripts_execute_in_shared_global_scope():
    result = subprocess.run(
        [node, str(SCRIPT)], cwd=ROOT, capture_output=True, timeout=30,
        text=True, encoding="utf-8", errors="replace",
    )
    assert result.returncode == 0, f"JS 冒烟测试失败:\n{result.stdout}\n{result.stderr}"
    assert "JS 冒烟测试通过" in result.stdout
