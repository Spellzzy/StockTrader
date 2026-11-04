@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo 正在启动 Stock Trader AI 本地界面...
echo 首次使用请先安装依赖：pip install -r requirements.txt
echo.

python -m app.cli web
if errorlevel 1 (
  echo.
  echo 启动失败。请确认已安装 Python 3.10+ 并执行：
  echo   pip install -r requirements.txt
  echo.
  pause
)
