#!/bin/bash
cd "$(dirname "$0")" || exit 1

echo "正在启动 Stock Trader AI 本地界面..."
echo "首次使用请先安装依赖：pip3 install -r requirements.txt"
echo

python3 -m app.cli web
