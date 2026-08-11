# Browser Action Adapter

通用 Chrome 扩展，作为 **Browser Action Adapter** 的执行端：任意智能体通过 Bridge API 下发 `BrowserCommand`，扩展在用户浏览器会话中执行 DOM 操作并回传 `PageState`。

## 架构

```
Agent (OpenClaw / Hermes SKILL / SDK / Ontology Connector)
        │  HTTP /v1/browser
        ▼
BrowserBridge (ontology-admin 内置，或独立进程)
        │  poll / steps
        ▼
Chrome Extension → 用户浏览器 Tab（SSO 会话）
```

## 安装

1. Chrome → `chrome://extensions` → 开发者模式 → 加载 `extension/`
2. 选项页设置 **Bridge 地址**（默认 `http://127.0.0.1:8080`）
3. API 版本选 **v1**（推荐）

## Agent 调用（Python SDK）

```python
from ontology_platform.browser_adapter import BrowserAdapterClient
from ontology_platform.browser_adapter.schema import BrowserCommand

client = BrowserAdapterClient("http://127.0.0.1:8080")

# 交互式 session
created = client.create_session(mode="interactive", start_url="https://example.com")
sid = created["session"]["id"]

state = client.snapshot(sid)
client.click(sid, selector="a")

# 声明式 script（扩展自动执行）
client.run_script(
    [
        {"action": "goto", "url": "https://example.com"},
        {"action": "snapshot"},
        {"action": "finish"},
    ],
    start_url="https://example.com",
)
```

## REST API（v1）

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/v1/browser/sessions` | 创建 session |
| `GET` | `/v1/browser/sessions/pending` | 扩展轮询 |
| `POST` | `/v1/browser/sessions/{id}/steps` | 扩展 step 循环 |
| `POST` | `/v1/browser/sessions/{id}/commands` | Agent 下发命令（interactive，long poll） |
| `GET` | `/v1/browser/sessions/{id}/steps/wait` | Agent 等待 step 结果 |

命令类型：`goto`, `click`, `fill`, `select`, `extract`, `scroll`, `wait`, `snapshot`, `finish`, `noop`。

## Session 模式

| mode | 说明 |
|------|------|
| `scripted` | YAML/JSON 步骤序列，扩展自动跑完 |
| `interactive` | Agent 通过 `/commands` 逐步驱动 |
| `async` | 创建 session 后等待 Agent 命令 |

## 兼容

- **legacy** API：`/api/browser/runs/*`（Ontology Connector 专用，扩展选项可切换）
- Ontology **Extension 采集** 仍走 Connector → Bridge → 扩展

## 模块位置

- Bridge：`src/ontology_platform/browser_adapter/`
- SDK：`ontology_platform.browser_adapter.sdk.BrowserAdapterClient`
- Ontology 集成：`src/ontology_platform/connector/browser/manager.py`
