---
name: ontology-browser
description: Control the user's Chrome via Browser Extension — local bridge only (127.0.0.1), no remote server. Snapshot, navigate, click, fill, scripted capture.
version: 1.0.0
metadata:
  openclaw:
    requires:
      bins:
        - ontology-browser-client
        - ontology-browser-bridge
    env:
      - BROWSER_BRIDGE_URL
  hermes:
    tags: [browser, chrome, extension, automation, capture]
    category: integration
---

# Ontology Browser（本机 Bridge + Chrome 扩展）

通过 **本机轻量 Bridge**（默认 `http://127.0.0.1:9920`）驱动用户 Chrome 中的扩展执行 DOM 操作。不需要单独部署远程中间服务器；Agent 与扩展都在同一台机器上，Bridge 只是本机 HTTP 守护进程。

## 前置条件

1. 已安装 Python 包：`pip install "ontology-agent-platform[browser]"`（或运行 `{baseDir}/../scripts/install.sh`）
2. Chrome 已加载 [Browser Extension](https://github.com/Jacksonhuf/terminalSample/releases)，Options 里 **Bridge URL** = `BROWSER_BRIDGE_URL`（默认 `http://127.0.0.1:9920`），API 选 **v1**
3. 本机 Bridge 已运行（见下方「启动 Bridge」）

## 启动 Bridge（本机即服务器）

```bash
# 若未运行，先确保 Bridge 起来（Skill 安装脚本也会做这件事）
ontology-browser-client ensure-bridge

# 或手动前台运行
ontology-browser-bridge --host 127.0.0.1 --port 9920 --db ~/.ontology/browser.db
```

验证：`ontology-browser-client health`

## 何时使用本 Skill

- 需要读取/操作**用户已登录**的 Web 页面（SSO、内网 ERP 等）
- 需要 snapshot、click、fill、声明式 script 采集
- **不要**用 Playwright 另开无会话浏览器替代（会丢失 SSO）

## 推荐调用方式（CLI，Agent 用 exec 工具）

环境变量（可选）：

```bash
export BROWSER_BRIDGE_URL=http://127.0.0.1:9920
```

### 1. 交互式 session（逐步操作）

```bash
# 创建 session
ontology-browser-client create-session --mode interactive --start-url https://example.com

# 对返回的 session_id 拍快照（扩展需在轮询）
ontology-browser-client snapshot <session_id> --timeout 60

# 查看状态
ontology-browser-client get-session <session_id>
```

### 2. 声明式 script（扩展自动逐步执行）

用 Python SDK 一次跑完（Agent 可 `python3 -c` 或调用 `{baseDir}/scripts/run-script.py`）：

```python
from ontology_platform.browser_adapter import BrowserAdapterClient
import os

client = BrowserAdapterClient(os.environ.get("BROWSER_BRIDGE_URL", "http://127.0.0.1:9920"))
session = client.run_script(
    [
        {"action": "goto", "url": "https://example.com"},
        {"action": "snapshot"},
        {"action": "finish"},
    ],
    start_url="https://example.com",
)
print(session["status"], session.get("data_count", 0))
```

### 3. 直接 REST（任意语言）

- `POST $BROWSER_BRIDGE_URL/v1/browser/sessions` — 创建 session
- `POST .../sessions/{id}/commands` — 下发 goto / click / snapshot / finish
- `GET .../sessions/pending` — 扩展轮询用

## 故障排查

| 现象 | 处理 |
|------|------|
| health 失败 | 运行 `ontology-browser-client ensure-bridge` |
| snapshot 超时 | 确认扩展已连接、Bridge URL 与端口一致 |
| 0 条数据 | interactive 模式需主动 snapshot/extract；scripted 需在 script 里 extract 或 finish 前传 records |

## 与 Ontology Admin 的关系

若本机已运行 `ontology-admin --port 8080`，可将 `BROWSER_BRIDGE_URL=http://127.0.0.1:8080`，**无需**再单独起 `ontology-browser-bridge`（Admin 内置 `/v1/browser`）。
