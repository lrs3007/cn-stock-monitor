#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ -x .venv312/bin/python ]; then
  MONITOR_PYTHON=.venv312/bin/python
elif [ -x .venv/bin/python ]; then
  MONITOR_PYTHON=.venv/bin/python
else
  echo '请先按 README 安装 Python 3.11+ 和依赖。'
  exit 1
fi
exec "$MONITOR_PYTHON" -m backend.mobile
