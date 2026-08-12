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

### 从 GitHub Release 安装（推荐）

1. 打开 [Releases](https://github.com/Jacksonhuf/terminalSample/releases)，下载 `browser-action-adapter-x.y.z.zip`
2. 解压到本地目录
3. Chrome → `chrome://extensions` → 开发者模式 → **加载已解压的扩展程序** → 选择解压后的文件夹

### 从源码安装（开发）

1. Chrome → `chrome://extensions` → 开发者模式 → 加载本仓库 `extension/` 目录
2. 选项页设置 **Bridge 地址**（默认 `http://127.0.0.1:8080`）
3. API 版本选 **v1**（推荐）

## 打包构建

本扩展**独立于 Python wheel**，在仓库根目录执行：

```bash
chmod +x scripts/build-extension.sh
./scripts/build-extension.sh
# 产物：dist/browser-action-adapter-<version>.zip
```

版本号来自 `extension/manifest.json` 的 `version` 字段。

### 发布 Release（维护者）

```bash
# 1. 更新 extension/manifest.json 中的 version
# 2. 提交并推送 main
# 3. 打 tag 触发 GitHub Actions 自动发布
git tag browser-extension-v0.1.0
git push origin browser-extension-v0.1.0
```

也可在 GitHub Actions 中手动运行 **Release Browser Extension** workflow（仅上传 artifact，不创建 Release）。

Tag 命名规则：`browser-extension-v*`（例如 `browser-extension-v0.1.0`）。

## 在其他智能体上安装调用

### 1. Chrome 扩展（用户浏览器）

从 [Releases](https://github.com/Jacksonhuf/terminalSample/releases) 安装，选项页 **Bridge URL** 指向 Bridge 服务地址。

### 2. Bridge 服务（HTTP API）

```bash
pip install -e ".[browser-bridge]"   # 或 pip install "git+https://github.com/Jacksonhuf/terminalSample.git@main[browser-bridge]"
ontology-browser-bridge --host 0.0.0.0 --port 9920 --db ./browser.db
```

验证：`curl http://127.0.0.1:9920/health`

### 3. 智能体客户端（OpenClaw / Hermes / 自研 Agent）

**方式 A：Skill 一键安装（推荐，本机 Bridge，无远程服务器）**

```bash
pip install -e ".[browser]"
ontology-browser-client install-skill --target openclaw   # 或 hermes / auto
# OpenClaw 也可：openclaw skills install ./skills/ontology-browser
```

**方式 B：仅 SDK / CLI**

```bash
pip install -e ".[browser-client]"
export BROWSER_BRIDGE_URL=http://127.0.0.1:9920
ontology-browser-client ensure-bridge   # 本机未起 Bridge 时自动启动
```

**Python SDK**

```python
from ontology_platform.browser_adapter import BrowserAdapterClient
client = BrowserAdapterClient("http://127.0.0.1:9920")
```

**CLI（无代码快速测通）**

```bash
ontology-browser-client health
ontology-browser-client create-session --mode interactive --start-url https://example.com
ontology-browser-client snapshot <session_id>
```

**任意语言**：直接 HTTP 调用 `/v1/browser/sessions` 与 `/v1/browser/sessions/{id}/commands`。

依赖清单见 `examples/agents/requirements-browser-client.txt`（客户端）与 `requirements-browser-bridge.txt`（Bridge）。

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
