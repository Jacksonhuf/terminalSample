# Ontology Agent Platform

基于 **Ontology（本体）** 和 **LangGraph** 的智能体搭建平台（**模式 A：纯自建**）。参考 Palantir Foundry 思路，将业务数据建模为可操作的对象、关系和动作，通过 LangGraph 编排智能体，并内置治理（审计 + RBAC）。

> 样机管理是本平台之上的**应用层**示例。完整架构说明见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│  体验层                                                      │
│  Chainlit (对话)  |  ontology-admin (本体管理/可视化)         │
├─────────────────────────────────────────────────────────────┤
│  编排层 — LangGraph                                          │
│  plan → execute → [approval interrupt] → respond             │
├─────────────────────────────────────────────────────────────┤
│  治理层 — Governance                                         │
│  RBAC 权限  |  Action 审计日志                               │
├─────────────────────────────────────────────────────────────┤
│  语义层 — OntologyService                                    │
│  Object / Link / Action                                      │
├─────────────────────────────────────────────────────────────┤
│  数据层 — Connector (入站) + Mapping + SQL 暂存              │
│  Computer Use | Browser Extension | File | API               │
│  Channel Adapter (IM / 邮件 / 跟催) — 出站                 │
└─────────────────────────────────────────────────────────────┘
```

## 核心概念

| 概念 | 说明 |
|------|------|
| **ObjectType** | 业务对象类型（如 Prototype、Person） |
| **Link** | 对象间关系（如 belongs_to、custodian） |
| **Action** | 可执行业务动作，支持审批门禁 + 角色权限 |
| **LangGraph** | 编排 plan / execute / approval / respond |
| **Governance** | 审计日志 + admin/operator/viewer 角色 |
| **Connector** | 入站采集（Computer Use / Browser Extension / File） |
| **Mapping** | 暂存数据字段 → Ontology 属性映射 |
| **Channel Adapter** | 出站 IM / 邮件 / 跟催 |

## 快速开始

### 环境要求

- Python **≥ 3.11**
- 本机演示无需 PostgreSQL、LLM、真实 IM/邮件；示例数据启动时自动注入

### 安装

```bash
pip install -e .
```

开发/跑测试时安装 dev 依赖：

```bash
pip install -e ".[dev]"
```

默认安装已包含 **Chainlit 对话界面**（`chainlit`）、**LangGraph 审批 checkpoint 持久化**（`langgraph-checkpoint-sqlite`）与 **Excel 本体导入**（`openpyxl`），可直接运行 `chainlit run chainlit_app.py`、审批工作台与 Admin Excel 导入。

可选 extras：

| Extra | 用途 |
|-------|------|
| `dev` | pytest |
| `chat` | 与默认安装相同（Chainlit）；保留以兼容旧命令 |
| `checkpoint` | 与默认安装相同（SQLite checkpoint）；保留以兼容旧命令 |
| `studio` | LangGraph Studio 调试 |
| `postgres` | PostgreSQL 持久化 |
| `capture` | LLM Computer Use 采集（Playwright 浏览器） |

### 本机业务演示（推荐）

适合在自己电脑上向业务方演示「对话查询 → 业务操作 → 审批 → 看板 → 审计」完整闭环。**不需要**配置 LLM、真实 ERP、IM 或邮件（默认规则引擎 + mock 通知即可）。

**1. 准备共享数据目录**（Chainlit 与 Admin 必须指向同一数据库）：

```bash
mkdir -p data
export ONTOLOGY_STORE_PATH=./data/demo.db
export ONTOLOGY_SEED=true
```

**2. 终端 A — 启动运营后台**：

```bash
ontology-admin \
  --store-path ./data/demo.db \
  --ontology-db ./data/demo.db \
  --port 8080
```

打开 http://localhost:8080/admin（统一运营后台，左侧菜单切换各功能）。

**3. 终端 B — 启动对话界面**：

```bash
chainlit run chainlit_app.py
```

打开 http://localhost:8000

**4. 建议演示话术**（在 Chainlit 中依次输入）：

| 步骤 | 输入 | 展示点 |
|------|------|--------|
| 1 | `查询所有可用样机` | 自然语言查询 → 结构化结果 |
| 2 | `SN-2024-001 归属哪个项目` | 关系遍历 |
| 3 | `样机看板统计` | 运营指标汇总 |
| 4 | `预约 SN-2024-003` | 审批门禁（弹出批准/拒绝按钮） |

批准后切换到运营中心（`/admin/operations/approvals`），展示看板变化与审计日志。可选补充页面：

- http://localhost:8080/admin/ontologies — 本体列表（新建 / 删除 / Excel 导入）
- http://localhost:8080/admin/ontologies/prototype/graph — 本体关系图
- http://localhost:8080/admin/integration/connectors — 数据采集配置
- http://localhost:8080/admin/settings/llm — LLM 配置（有内网模型时可现场演示）

> **提示**：若 `ontology-admin` / `chainlit` 命令找不到，改用 `python3 -m ontology_platform.admin` 与 `python3 -m chainlit run chainlit_app.py`。Admin 仅供本机/内网演示，勿暴露到公网（当前无登录鉴权）。

### 运行 Demo（命令行）

```bash
# 平台 Demo（Person/Project）
ontology-platform --seed --query "查询所有 Person"

# 样机管理应用
ontology-platform --app prototype --seed --query "查询所有可用样机"
```

### Chainlit 对话界面（智能体前端）

本机演示见上方 [本机业务演示](#本机业务演示推荐)。单独启动：

```bash
export ONTOLOGY_STORE_PATH=./data/demo.db   # 可选，启用持久化与审批 checkpoint
chainlit run chainlit_app.py
```

浏览器打开 http://localhost:8000，可尝试：

- `查询所有可用样机`
- `SN-2024-001 归属哪个项目`
- `预约 SN-2024-003`（弹出批准/拒绝按钮）

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `ONTOLOGY_APP` | `prototype` | `prototype` 或 `demo` |
| `ONTOLOGY_STORE_PATH` | — | SQLite 持久化路径 |
| `ONTOLOGY_INTEGRATIONS_DB` | 同 store | 消息日志与跟催任务库 |
| `ONTOLOGY_SEED` | `true` | 启动时注入示例数据 |
| `ONTOLOGY_USER_ID` | `anonymous` | 未启用 Chainlit 登录时的用户 ID |
| `ONTOLOGY_USER_ROLES` | `operator` | 未启用登录时的角色（逗号分隔） |
| `ONTOLOGY_APPROVER_ROLES` | `admin` | 未启用登录时审批使用的角色 |
| `ONTOLOGY_ROLE_MAP` | — | JSON：用户 ID 前缀 → 角色列表 |

### 本体管理界面 & 可视化

本机演示见上方 [本机业务演示](#本机业务演示推荐)。单独启动：

```bash
ontology-admin --port 8080
# 指定本体 YAML 目录：ontology-admin --dir ./my_ontologies --port 8080
```

**统一入口**：http://localhost:8080/admin（左侧菜单 + `/admin/*` 路由，单页应用无需整页刷新）。旧路径（如 `/operations`、`/editor`、`/visualize`）会自动 302 重定向。

| 模块 | 地址 | 功能 |
|------|------|------|
| 本体列表 | `/admin/ontologies` | 查看 / 新建 / 删除本体 |
| 本体编辑器 | `/admin/ontologies/{name}/edit` | 编辑对象类型、属性、关系、动作，保存 YAML |
| 本体图谱 | `/admin/ontologies/{name}/graph` | 交互式关系可视化 |
| 运营中心 | `/admin/operations/overview` | 平台概览、审批、审计、消息、跟催 |
| 应用示例 | `/admin/apps/prototype/dashboard` | 样机管理应用看板（演示） |
| 数据连接 | `/admin/integration/connectors` | Connector 配置、凭据、Computer Use / Extension 采集 |
| 数据映射 | `/admin/integration/mappings/discover` | 暂存数据浏览、字段映射、同步到 Ontology |
| LLM 配置 | `/admin/settings/llm` | 模型、代理、内网 bypass |

启动时指定数据路径以启用运营与集成功能（与 Chainlit 共用同一路径）：

```bash
ontology-admin \
  --port 8080 \
  --store-path ./data/demo.db \
  --ontology-db ./data/demo.db \
  --connector-db ./data/connector.db
```

#### Excel 批量导入本体

适合从零搭建或批量维护本体结构，无需手写 YAML：

1. 打开 **本体列表** → 点击 **「下载 Excel 模板」**
2. 按工作表填写：`ontology`（元数据）、`object_types`、`properties`、`links`、`actions`、`action_params`
3. 点击 **「导入 Excel」** 上传 `.xlsx`；若同名本体已存在，可勾选 **覆盖已有同名本体**

也可通过 API：

```bash
# 下载模板（含示例行与填写说明）
curl -OJ http://localhost:8080/api/ontologies/import/template

# 导入
curl -X POST "http://localhost:8080/api/ontologies/import?overwrite=false" \
  -F "file=@my_ontology.xlsx"
```

导入校验包括：对象类型引用、关系端点、动作目标类型、动作参数归属等；通过后写入 `{name}.yaml`（目录由 `--dir` 指定，默认 `examples/`）。

#### 本体编辑器说明

- **概览**：修改版本、描述
- **对象类型 / 关系 / 动作**：支持添加、编辑、删除（编辑后需点顶部 **保存** 写入文件）
- **JSON**：直接编辑完整本体 JSON 并应用

相关 REST API：`GET/POST/PUT/DELETE /api/ontologies`、`/api/ontologies/{name}/object-types` 等。

| 页面（旧，仍可用） | 重定向至 |
|-------------------|----------|
| `/` | `/admin` |
| `/editor` | `/admin/ontologies/edit` |
| `/visualize` | `/admin/ontologies/graph` |
| `/operations` | `/admin/operations/overview` |
| `/admin/operations/dashboard` | `/admin/apps/prototype/dashboard` |
| `/connectors` | `/admin/integration/connectors` |
| `/mappings` | `/admin/integration/mappings/discover` |
| `/settings/llm` | `/admin/settings/llm` |

审计日志 API：`GET /api/audit-logs`（需 `--store-path`）。

### LangGraph Studio（编排调试）

```bash
langgraph dev
```

可视化调试 `plan → execute → approval → respond` 全流程。入口：`langgraph_studio.py`。

### 治理：审计日志 + RBAC

```python
from ontology_platform import AgentConfig, PrototypeApp

config = AgentConfig(store_path="./data.db", enable_governance=True)
app = PrototypeApp.create(config=config)
app.seed()

# operator 发起写操作
app.platform.chat("预约 SN-2024-003", user_id="zhangsan", roles=["operator"])

# admin 审批
app.platform.resume(approved=True, roles=["admin"])

# 查询审计日志
for log in app.platform.get_audit_logs(action_name="ReservePrototype"):
    print(log.timestamp, log.user_id, log.status, log.message)
```

**内置角色：**

| 角色 | 权限 |
|------|------|
| admin | 查询 + 全部动作 + 审批 |
| operator | 查询 + 普通写操作 |
| viewer | 仅查询 |

在 Ontology YAML 中为 Action 配置权限：

```yaml
actions:
  - name: ReservePrototype
    allowed_roles: [operator, admin]
    approver_roles: [admin]
    requires_approval: true
```

### 样机管理应用

```python
from ontology_platform import PrototypeApp

app = PrototypeApp.create()
app.seed()
print(app.chat("查询 X100 型号样机"))
print(app.chat("样机看板统计"))
print(app.dashboard_text())
```

详见 `examples/prototype_ontology.yaml`（Prototype / Person / Project / Location / Reservation + 12 个动作，含调拨、送修、看板与 IM/邮件通知）。

### PostgreSQL 持久化

```bash
export ONTOLOGY_DATABASE_URL=postgresql://user:pass@localhost:5432/ontology
ontology-platform --app prototype --database-url "$ONTOLOGY_DATABASE_URL" --seed
```

`AgentConfig` 支持 `store_backend=postgres` 或 `auto`（检测 `database_url`）。安装：`pip install -e ".[postgres]"`。

LangGraph 审批状态默认持久化到 `{store}.checkpoints.db`（默认安装已包含 `langgraph-checkpoint-sqlite`）。

### 审批工作台

运营中心「审批工作台」Tab 可查看 pending 审批，并直接批准/拒绝。需与 Chainlit 配置相同的 `--store-path`，以共享运行时 checkpoint：

```bash
ontology-admin --store-path ./data/demo.db --ontology-db ./data/demo.db --port 8080
# http://localhost:8080/admin/operations/approvals（支持批量批准）
```

### Outbound Channels（IM / 邮件 / 跟催）

通过 Ontology Action 触发内部 IM 或邮件通知，支持定时跟催：

```bash
# 处理到期跟催（建议 cron 或守护进程）
ontology-outreach run
ontology-outreach daemon --interval 60

# 查看发送记录
ontology-outreach logs --object-type Prototype --object-id SN-2024-002
ontology-outreach tasks --status pending
```

| Action | 说明 |
|--------|------|
| `NotifyCustodian` | IM 通知样机保管人 |
| `SendChatMessage` | 向指定人员发 IM（需审批） |
| `SendEmailReminder` | 立即邮件跟催（需审批） |
| `ScheduleReminder` | 预约定时跟催 |

配置环境变量以对接内部 CLI（默认 `im-cli` / `mail-cli`，开发模式 `ONTOLOGY_EMAIL_MODE=mock`）：

```bash
export ONTOLOGY_CHAT_CLI=im-cli
export ONTOLOGY_EMAIL_MODE=smtp
export ONTOLOGY_SMTP_HOST=mail.example.com
```

`Person` 对象需配置 `im_user_id` 和 `email`。完整说明见 [ARCHITECTURE.md](ARCHITECTURE.md#6-出站集成channel-adapterim--邮件--跟催)。

### Data Connector（入站采集 → SQL 暂存 → Ontology）

从外部系统采集数据，写入 SQL 暂存区，经映射同步到本体。支持四种连接器模式：

| 模式 | 说明 | 典型场景 |
|------|------|----------|
| `computer_use` | 服务端 LLM + Playwright 驱动浏览器 | 批量采集、无人值守 |
| `browser_extension` | Chrome 扩展在用户会话中执行 YAML 脚本 | SSO 登录站点、需人工会话 |
| `file` | 本地 JSON / 文件导入 | 离线、对接导出文件 |
| `api` | HTTP API 拉取（预留） | 有开放接口的系统 |

采集链路：`Connector 定义 → 采集执行 → CaptureBatch ingest → Mapping sync → OntologyService`

#### LLM Computer Use 自动采集（`computer_use`）

配置连接器 + 凭据 + LLM 后，可一键或定时执行完整采集链路（浏览器操作 → ingest → sync）：

```bash
# 安装浏览器依赖（真实 LLM 采集需要）
pip install -e ".[capture]"
playwright install chromium

# 手工触发采集（使用 Admin 配置的 LLM）
ontology-connector run prototype_erp \
  --db ./data/connector.db \
  --credential-db ./data/demo.db \
  --ontology examples/prototype_ontology.yaml \
  --ontology-db ./data/demo.db

# 演示模式（使用 examples/captures 样例数据，无需 LLM/浏览器）
ontology-connector run prototype_erp --mock --db ./data/connector.db

# 定时采集守护进程（按连接器 schedule 配置轮询）
ontology-connector daemon --interval 60 \
  --db ./data/connector.db \
  --credential-db ./data/demo.db \
  --ontology examples/prototype_ontology.yaml \
  --ontology-db ./data/demo.db
```

Admin **数据连接** 页面（`/admin/integration/connectors`）：

- **立即采集** — 调用已配置 LLM + Playwright 执行采集（`computer_use`）
- **演示采集 (Mock)** — 使用样例 JSON，适合本机演示
- **Extension 采集** — 创建浏览器扩展任务，由 Chrome 扩展在用户会话中执行（`browser_extension`）
- **启用定时采集** — 设置 `interval_sec`，配合 `ontology-connector daemon` 无人值守运行

#### Chrome Browser Extension 采集（`browser_extension`）

适用于只有 Web 界面、且依赖用户 SSO 会话的系统。扩展是**通用协议执行器**，可被 Ontology Connector、OpenClaw、Hermes SKILL 或任意 Agent 通过 **Browser Bridge API** 驱动。

```
Agent / Connector  →  BrowserBridge (/v1/browser)  →  SQLite (browser_sessions)
                              ↑
                    Chrome Extension（轮询 + DOM 执行）
                              ↓
              Ontology ingest（可选）| webhook | JSON data
```

**安装扩展**：

1. **Release（推荐）**：从 [GitHub Releases](https://github.com/Jacksonhuf/terminalSample/releases) 下载 `browser-action-adapter-x.y.z.zip`，解压后加载
2. **源码**：Chrome 打开 `chrome://extensions` → 开发者模式 → 「加载已解压的扩展程序」→ 选择仓库 `extension/` 目录
3. 扩展选项中设置 Bridge 地址（默认 `http://127.0.0.1:8080`），API 版本选 **v1**

维护者打包：`./scripts/build-extension.sh` → `dist/browser-action-adapter-<version>.zip`；发布 tag `browser-extension-v*` 触发 CI Release。

**Ontology Connector 采集**：

```bash
curl -X POST http://localhost:8080/api/connectors/browser_demo/browser-run \
  -H 'Content-Type: application/json' \
  -d '{"auto_sync": false}'
```

**任意 Agent 驱动（Python SDK）**：

```python
from ontology_platform.browser_adapter import BrowserAdapterClient

client = BrowserAdapterClient("http://127.0.0.1:8080")
created = client.create_session(mode="interactive", start_url="https://example.com")
sid = created["session"]["id"]
client.snapshot(sid)  # 需扩展正在轮询
```

**通用 REST API**：`POST /v1/browser/sessions`、`POST /v1/browser/sessions/{id}/commands`（interactive）、`GET /v1/browser/sessions/pending`（扩展轮询）。详见 [extension/README.md](extension/README.md)。

Legacy Connector API（`/api/browser/runs/*`）仍可用；模块位于 `src/ontology_platform/browser_adapter/`。

#### Browser Action Adapter（通用浏览器执行端）

Chrome 扩展 + Browser Bridge 组成**与 Ontology 解耦**的浏览器执行层，任意智能体均可调用。

| 组件 | 路径 | 说明 |
|------|------|------|
| Chrome 扩展 | `extension/` | DOM 执行器（goto / click / fill / snapshot / extract …） |
| Browser Bridge | `src/ontology_platform/browser_adapter/` | Session 队列、step 协议、REST API |
| Python SDK | `browser_adapter.sdk.BrowserAdapterClient` | Agent / 脚本调用入口 |
| Ontology 集成 | `connector/browser/manager.py` | Connector 采集完成后 ingest（可选） |
| Agent 示例 | `examples/agents/browser_agent_demo.py` | interactive 模式 demo |

**Session 模式**

| mode | 驱动方 | 说明 |
|------|--------|------|
| `scripted` | YAML/JSON 脚本 | 扩展自动逐步执行，适合固定采集流程 |
| `interactive` | Agent 逐步发命令 | 通过 `/commands` long poll，适合 OpenClaw / LLM Agent |
| `async` | Agent 按需发命令 | 创建 session 后等待 Agent 下发命令 |

**v1 REST API**（随 `ontology-admin` 启动，默认 `http://127.0.0.1:8080`）

| 方法 | 路径 | 调用方 |
|------|------|--------|
| `POST` | `/v1/browser/sessions` | Agent — 创建 session |
| `GET` | `/v1/browser/sessions/{id}` | Agent — 查询状态 |
| `DELETE` | `/v1/browser/sessions/{id}` | Agent — 取消 |
| `POST` | `/v1/browser/sessions/{id}/commands` | Agent — interactive 下发命令（long poll 等结果） |
| `GET` | `/v1/browser/sessions/{id}/steps/wait` | Agent — 等待扩展 step 结果 |
| `GET` | `/v1/browser/sessions/pending` | 扩展 — 轮询待执行 session |
| `POST` | `/v1/browser/sessions/{id}/steps` | 扩展 — step 循环（上报结果 + 取下一条命令） |
| `POST` | `/v1/browser/sessions/{id}/heartbeat` | 扩展 — 心跳 |

**安装命令（部署到其他智能体 / 环境）**

三套组件可分开安装：

| 组件 | 安装命令 | 说明 |
|------|----------|------|
| **Chrome 扩展** | [GitHub Release zip](https://github.com/Jacksonhuf/terminalSample/releases) | 无需 pip，解压后在 Chrome 加载 |
| **Bridge 服务** | 见下方 | 与扩展 HTTP 通信，可单独部署 |
| **Agent 客户端** | 见下方 | 安装 SDK，在 OpenClaw / Hermes / 自研 Agent 中调用 |

```bash
# ── 方式 A：从本仓库安装（开发 / 内网）──

# Bridge 服务机（只需 API，不要 Admin UI）
pip install -e ".[browser-bridge]"
ontology-browser-bridge --host 0.0.0.0 --port 9920 --db ./browser.db

# 智能体所在机器（Python Agent / SKILL 后端）
pip install -e ".[browser-client]"
export BROWSER_BRIDGE_URL=http://<bridge-host>:9920
ontology-browser-client health
ontology-browser-client create-session --start-url https://example.com

# 一次装齐 Bridge + Client
pip install -e ".[browser]"

# ── 方式 B：从 GitHub 安装（其他机器 clone 不便时）──

pip install "git+https://github.com/Jacksonhuf/terminalSample.git@main#egg=ontology-agent-platform[browser]"

# ── 方式 C：已跑 Ontology Admin 时可不单独起 Bridge ──

pip install -e ".[browser-client]"
export BROWSER_BRIDGE_URL=http://127.0.0.1:8080   # ontology-admin 内置 /v1/browser
```

**在智能体代码中调用**

```python
import os
from ontology_platform.browser_adapter import BrowserAdapterClient

client = BrowserAdapterClient(os.environ.get("BROWSER_BRIDGE_URL", "http://127.0.0.1:9920"))
created = client.create_session(mode="interactive", start_url="https://example.com")
sid = created["session"]["id"]
client.snapshot(sid)   # 需用户 Chrome 已装扩展并指向同一 Bridge
```

Shell / 非 Python 智能体可直接调 REST：`POST $BROWSER_BRIDGE_URL/v1/browser/sessions`，详见上文 API 表。

**快速验证**

```bash
# 1. 启动 Bridge（二选一）
ontology-browser-bridge --port 9920 --db ./browser.db          # 轻量独立服务
# ontology-admin --port 8080 --connector-db ./data/connector.db  # 或完整 Admin

# 2. 创建 scripted session（扩展需已加载并在轮询）
curl -X POST http://localhost:8080/v1/browser/sessions \
  -H 'Content-Type: application/json' \
  -d '{
    "mode": "scripted",
    "start_url": "https://example.com",
    "script": [
      {"action": "goto", "url": "https://example.com"},
      {"action": "snapshot"},
      {"action": "finish"}
    ]
  }'

# 3. Python SDK 交互式 demo
python3 examples/agents/browser_agent_demo.py http://127.0.0.1:8080
```

**实现状态**

| 能力 | 状态 |
|------|------|
| Chrome 扩展 + v1/legacy API | ✅ |
| scripted / interactive / async session | ✅ |
| Python SDK（`BrowserAdapterClient`） | ✅ |
| Ontology Connector ingest 集成 | ✅ |
| MCP Server / Hermes SKILL 模板 | 待后续（可基于 SDK 封装） |
| API Key 鉴权 / WebSocket | 待后续 |

更多细节见 [extension/README.md](extension/README.md)。

#### 手动分步流程（兼容旧方式）

```bash
# 1. 生成 Computer Use 采集任务（含 run_id 与操作说明）
ontology-connector task prototype_erp

# 2. Computer Use 完成后，将采集 JSON 入库
ontology-connector ingest examples/captures/prototype_erp_sample.json

# 3. 映射同步到 Ontology
ontology-connector sync prototype_erp

# 离线模式：从本地 JSON 文件直接同步（无需 Computer Use）
ontology-connector ingest-file prototype_file

# 查看运行状态
ontology-connector status prototype_erp
ontology-connector list
```

Connector 定义见 `examples/connectors/`，采集样例见 `examples/captures/`。完整说明见 [ARCHITECTURE.md](ARCHITECTURE.md#5-数据层data-connectorcomputer-use--sql--ontology)。

### 数据映射工作台（Staging → Ontology）

集成数据进入暂存区后，通过 Admin **数据映射** 页面配置与 Ontology 的关联（无需在集成时预知本体结构）：

1. **数据源浏览** — 查看各 Connector / `record_type` 的暂存条数与样本字段
2. **映射配置** — 配置源字段 → Ontology 属性，支持试跑预览
3. **同步任务** — 发布 `active` 映射后执行同步，写入 Ontology 实例库

```bash
ontology-admin --store-path ./data/demo.db --connector-db ./data/connector.db --port 8080
# http://localhost:8080/admin/integration/mappings/discover
```

映射配置存储在 `mapping.db`（默认与 connector 库同目录）。同一 `(connector, record_type)` 仅允许一个 `active` 映射；未配置 active 映射时，回退使用 Connector YAML 中的 `record_mappings`。

## 项目结构

### 总览

```
ontology-agent-platform/
├── chainlit_app.py              # Chainlit 对话入口
├── langgraph_studio.py          # LangGraph Studio 调试入口
├── langgraph.json               # LangGraph Studio 配置
├── pyproject.toml               # 包定义、CLI 入口、可选依赖
├── README.md                    # 本文件（快速开始 + 结构说明）
├── ARCHITECTURE.md              # 架构决策、Palantir 映射、治理细节
│
├── extension/                   # Chrome Extension — Browser Action Adapter
│   ├── manifest.json            # MV3 扩展清单
│   ├── background/              # Service Worker：轮询任务、协调 Tab
│   ├── content/                 # Content Script：DOM 命令执行
│   ├── sidepanel/               # 任务状态侧栏
│   ├── options/                 # 平台地址、轮询间隔配置
│   └── README.md                # 扩展安装与协议说明
│
├── examples/                    # 示例本体、连接器与采集数据
│   ├── prototype_ontology.yaml  # 样机管理本体（应用层示例）
│   ├── demo_ontology.yaml         # 通用 Demo 本体
│   ├── connectors/              # Connector YAML（erp / file / browser_demo）
│   ├── captures/                # Computer Use 采集样例 JSON
│   ├── agents/                  # Agent 驱动 Browser Bridge 示例
│   └── data/                    # Seed 数据
│
├── src/ontology_platform/       # 平台核心 Python 包
│   └── …                        # 见下方「源码包分层」
│
└── tests/                       # pytest 测试（152+ 用例）
```

### 源码包分层

`src/ontology_platform/` 按**体验 → 编排 → 治理 → 语义 → 数据**分层组织：

| 目录 | 层级 | 职责 |
|------|------|------|
| `admin/` | 体验层 | FastAPI 运营后台 + SPA（本体/集成/运营/LLM） |
| `chat/` | 体验层 | Chainlit 用户身份、RBAC 映射辅助 |
| `agent/` | 编排层 | LangGraph 图、节点、Planner、Tools |
| `governance/` | 治理层 | 审计日志、RBAC 策略、审批存储 |
| `ontology/` | 语义层 | Object / Link / Action 模型、Registry、Store |
| `connector/` | 数据层（入站） | 连接器管理、凭据、采集、暂存、同步 |
| `mapping/` | 数据层（入站） | 暂存字段 → Ontology 属性映射配置 |
| `integrations/` | 数据层（出站） | IM / 邮件 Channel、跟催任务 Worker |
| `llm/` | 基础设施 | LLM Profile 存储、工厂、HTTP 代理 |
| `apps/` | 应用层 | 样机管理应用（PrototypeApp、看板、分析） |
| `platform.py` | 入口 | `AgentPlatform` — 对话、动作、审批、审计 |
| `runtime.py` | 入口 | Admin / API 用运行时平台构建 |
| `cli.py` | 入口 | `ontology-platform` 命令行 |

### 目录详解

```
src/ontology_platform/
├── platform.py                  # AgentPlatform：chat / execute / resume / audit
├── runtime.py                   # build_runtime_platform() — Admin 与 Chainlit 共用
├── cli.py                       # ontology-platform CLI
│
├── ontology/                    # 语义层 — Ontology 核心
│   ├── schema.py                # ObjectType / Link / Action / Property 定义
│   ├── registry.py              # 从 YAML 加载本体
│   ├── service.py               # CRUD、Link 遍历、Action 执行
│   └── store/                   # 持久化：memory / sqlite / postgres
│
├── agent/                       # 编排层 — LangGraph
│   ├── graph.py                 # plan → execute → approval → respond
│   ├── nodes.py                 # 各节点实现
│   ├── planner.py               # LLM / 规则 Planner
│   ├── tools.py                 # Ontology 查询与动作 Tool
│   ├── state.py                 # Graph State
│   └── config.py                # AgentConfig（store、governance、LLM）
│
├── governance/                  # 治理层
│   ├── audit.py                 # AuditLogger — Action 审计
│   ├── policy.py                # RBAC PolicyEngine
│   ├── approval_store.py        # 审批请求持久化
│   └── context.py               # 用户/角色上下文
│
├── connector/                   # 数据层 — 入站 Connector
│   ├── schema.py                # ConnectorDef、CaptureBatch、CaptureMode
│   ├── manager.py               # 加载 YAML、ingest、sync_to_ontology
│   ├── store.py                 # connector.db — 运行记录与暂存记录
│   ├── credential_store.py      # 凭据库（加密存储）
│   ├── cli.py                   # ontology-connector CLI
│   ├── worker.py                # 定时采集守护进程
│   ├── capture/                 # LLM + Playwright Computer Use
│   │   ├── runner.py            # 采集编排入口
│   │   ├── llm_agent.py         # LLM 浏览器 Agent
│   │   └── browser.py           # Playwright 封装
│   └── browser/                 # Chrome Extension 协议 + Ontology 集成
│       ├── schema.py            # BrowserCommand / PageState
│       ├── step_engine.py       # scripted 步骤解析
│       └── manager.py           # 包装 BrowserBridge + ingest
│
├── browser_adapter/             # 通用 Browser Bridge（Agent 可调用）
│   ├── bridge.py                # Session 编排（scripted / interactive）
│   ├── store.py                 # browser_sessions（SQLite）
│   ├── api.py                   # /v1/browser REST 路由
│   ├── schema.py                # Session / Step 协议模型
│   └── sdk.py                   # BrowserAdapterClient
│
├── mapping/                     # 数据层 — 映射工作台
│   ├── schema.py                # MappingProfile、FieldRule
│   ├── store.py                 # mapping.db
│   └── service.py               # 发现、试跑、同步
│
├── integrations/                # 数据层 — 出站 Channel Adapter
│   ├── channels/                # chat_cli / email 实现
│   ├── outreach/                # 跟催任务 Store + Worker
│   ├── notification.py          # 通知服务门面
│   ├── message_log.py           # 消息发送记录
│   └── cli.py                   # ontology-outreach CLI
│
├── llm/                         # LLM 基础设施
│   ├── schema.py                # LlmProfile、ProxyConfig
│   ├── store.py                 # Profile 持久化
│   ├── factory.py               # ChatModel 工厂、连接测试
│   └── proxy.py                 # Admin → 模型网关 HTTP 代理
│
├── apps/                        # 应用层示例
│   ├── prototype.py             # PrototypeApp — 样机管理
│   ├── prototype_tools.py       # 样机专用 Agent Tools
│   └── prototype_analytics.py   # 看板统计
│
├── chat/                        # Chainlit 辅助
│   ├── identity.py              # 用户 ID / 角色解析
│   └── chainlit_helpers.py      # 审批按钮、消息格式化
│
└── admin/                       # 运营后台（FastAPI + SPA）
    ├── __main__.py              # ontology-admin CLI 入口
    ├── server.py                # FastAPI 路由（/api/* + 静态 SPA）
    ├── manager.py               # Ontology YAML 文件管理
    ├── excel_import.py          # Excel 批量导入本体
    ├── connectors_api.py        # Connector / 凭据 API
    ├── browser_api.py           # Browser Extension Run API 模型
    ├── mapping_api.py           # 映射工作台 API
    ├── llm_api.py               # LLM / 代理 API
    └── static/                  # 前端 SPA 资源
        ├── app.html / app.js    # Shell 入口
        ├── shell.js             # 路由、侧边栏菜单
        ├── style.css
        ├── partials/            # 各页面 HTML 片段
        └── modules/             # 各模块 JS（ontologies / connectors / …）
```

### Admin SPA 模块与路由

| 菜单分组 | 路由 | 前端模块 | 后端 API 域 |
|----------|------|----------|-------------|
| 本体建模 | `/admin/ontologies` | `ontologies.js` | `/api/ontologies` |
| 本体建模 | `/admin/ontologies/{name}/edit` | `editor.js` | `/api/ontologies/{name}` |
| 本体建模 | `/admin/ontologies/{name}/graph` | `graph.js` | `/api/ontologies/{name}` |
| 数据集成 | `/admin/integration/connectors` | `connectors.js` | `/api/connectors`、`/api/browser/runs`、`/v1/browser` |
| 数据集成 | `/admin/integration/credentials` | `connectors.js` | `/api/credentials` |
| 数据集成 | `/admin/integration/mappings/*` | `mappings.js` | `/api/mappings` |
| 运营中心 | `/admin/operations/*` | `operations.js` | `/api/audit-logs`、`/api/approvals`、… |
| 应用示例 | `/admin/apps/prototype/dashboard` | `prototype_app.js` | `/api/prototype/dashboard` |
| 系统设置 | `/admin/settings/llm` | `llm.js` | `/api/llm/profiles` |

### CLI 入口

| 命令 | 模块 | 用途 |
|------|------|------|
| `ontology-platform` | `cli.py` | 命令行对话 / Demo |
| `ontology-admin` | `admin/__main__.py` | 启动运营后台 Web 服务 |
| `ontology-connector` | `connector/cli.py` | 采集、ingest、sync、daemon |
| `ontology-outreach` | `integrations/cli.py` | 跟催任务 run / daemon / logs |
| `chainlit run chainlit_app.py` | 根目录 | 启动对话界面 |
| `langgraph dev` | `langgraph_studio.py` | LangGraph Studio 调试 |

### 数据文件（运行时）

启动时通过 CLI 参数或环境变量指定，**Chainlit 与 Admin 应共用同一路径**：

| 文件 | 参数 / 变量 | 内容 |
|------|-------------|------|
| `demo.db` | `--store-path` / `ONTOLOGY_STORE_PATH` | Ontology 实例、审计、审批 checkpoint |
| `connector.db` | `--connector-db` | Connector 运行记录、暂存记录、browser_runs |
| `mapping.db` | `--mapping-db` | 字段映射 Profile |
| `{name}.yaml` | `--dir` | 本体定义文件（默认 `examples/`） |
| `examples/connectors/*.yaml` | `--connectors-dir` | 连接器定义 |

### 测试

```
tests/
├── test_platform.py / test_prototype.py   # 平台与应用
├── test_connector*.py / test_capture_*.py # 数据连接与采集
├── test_browser_extension.py              # Browser Extension + Connector 集成
├── test_browser_adapter.py                # 通用 Browser Bridge / SDK
├── test_mapping.py                        # 映射工作台
├── test_governance.py / test_admin.py   # 治理与 Admin API
├── test_llm_*.py                          # LLM 配置
└── test_integrations.py / test_chainlit*.py
```

```bash
pytest   # 全量测试（147+ 用例）
```

## 版本说明

当前版本 **v0.1.0** 定位为**技术预览 / 本机·内网演示**：

| 场景 | 是否适合 |
|------|----------|
| 本机向业务方演示 | ✅ |
| 内网 PoC / 二次开发 | ✅ |
| 公网生产部署 | ❌（缺 Admin 鉴权、一键部署包；见扩展路线） |

## 扩展路线

- [x] Outbound Channels（IM / 邮件 / 跟催）
- [x] Data Connector（Computer Use / File → SQL → Ontology）
- [x] Browser Extension Action Adapter（Chrome 扩展 + browser_script 协议）
- [x] Browser Bridge 通用 API（/v1/browser + Python SDK，Agent 可驱动）
- [x] 审计日志 / 消息 / 跟催 admin 运营中心
- [x] outreach 守护进程 (`ontology-outreach daemon`)
- [x] Chainlit 用户身份与 RBAC 对接（含角色映射）
- [x] PostgreSQL 持久化（Ontology Store）
- [x] 审批工作台（admin 运营中心）
- [ ] Neo4j 图库持久化
- [ ] LDAP / SSO 用户集成
- [ ] 自研 Logic 可视化编辑器（长期）
- [x] LLM Planner
- [x] 审批流（LangGraph interrupt）
- [x] SQLite 持久化
- [x] Chainlit 对话前端
- [x] 本体管理 & 可视化 UI（统一 Admin Shell、Excel 导入）
- [x] Action 审计 + RBAC
