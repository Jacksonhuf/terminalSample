#!/usr/bin/env bash
# Browser Extension + Ontology Admin 联调脚本
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PORT="${ADMIN_PORT:-8080}"
ADMIN_URL="http://127.0.0.1:${PORT}"
DB="${CONNECTOR_DB:-./data/connector.db}"
SIMULATE=false

for arg in "$@"; do
  case "$arg" in
    --simulate) SIMULATE=true ;;
  esac
done

mkdir -p "$(dirname "$DB")"
echo "==> 安装依赖 ..."
python3 -m pip install -e ".[browser]" -q

echo "==> 配置说明 ..."
python3 -m ontology_platform.browser_adapter.cli_quickstart setup --admin

if curl -sf "${ADMIN_URL}/v1/browser/sessions/pending" >/dev/null 2>&1; then
  echo "==> Admin 已在 ${ADMIN_URL} 运行"
else
  echo "==> 启动 ontology-admin (port ${PORT}) ..."
  python3 -m ontology_platform.admin.__main__ --port "$PORT" --connector-db "$DB" &
  ADMIN_PID=$!
  trap 'kill $ADMIN_PID 2>/dev/null || true' EXIT
  for i in $(seq 1 30); do
    if curl -sf "${ADMIN_URL}/v1/browser/sessions/pending" >/dev/null 2>&1; then
      break
    fi
    sleep 0.5
  done
fi

echo ""
echo "请确认 Chrome 扩展 Options → Bridge URL = ${ADMIN_URL}，API = v1"
if [[ "$SIMULATE" == true ]]; then
  echo "==> 模拟扩展执行（无需 Chrome）..."
  ONTOLOGY_ADMIN_URL="$ADMIN_URL" ontology-browser-client test-admin-capture --simulate
else
  echo "扩展就绪后运行:"
  echo "  ONTOLOGY_ADMIN_URL=${ADMIN_URL} ontology-browser-client test-admin-capture"
fi
