#!/usr/bin/env bash
# 一键：安装依赖 → 启动本机 Bridge → 打印扩展配置说明 → 可选立即测采集
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

RUN_TEST=false
for arg in "$@"; do
  case "$arg" in
    --test) RUN_TEST=true ;;
  esac
done

echo "==> 安装 Python 包 [browser] ..."
python3 -m pip install -e ".[browser]" -q

echo "==> 启动本机 Bridge + 配置说明 ..."
python3 -m ontology_platform.browser_adapter.cli_quickstart setup --url "${BROWSER_BRIDGE_URL:-http://127.0.0.1:9920}"

if [[ "$RUN_TEST" == true ]]; then
  echo ""
  echo "==> 运行采集测试（请先按上方说明配置 Chrome 扩展）..."
  read -r -p "扩展已配置并显示已连接？按 Enter 继续，Ctrl+C 取消 "
  python3 -m ontology_platform.browser_adapter.cli_quickstart test-capture
else
  echo ""
  echo "扩展配置好后运行:"
  echo "  ontology-browser-client test-capture"
  echo "或:"
  echo "  ./scripts/browser-quickstart.sh --test"
fi
