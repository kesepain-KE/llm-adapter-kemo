#!/usr/bin/env bash
# Kemo LLM Adapter — Linux / macOS 启动脚本
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 加载 provider 密钥
if [ -f provider.env ]; then
  set -a
  # shellcheck disable=SC1091
  source provider.env
  set +a
  echo "[kemo] loaded provider.env"
fi

# 创建运行数据目录
mkdir -p data_status/call_log

echo "[kemo] starting server..."
exec python3 server.py "$@"
