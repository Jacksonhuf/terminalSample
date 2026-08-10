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
│  数据层 — Connector (入站) + Channel Adapter (出站) + SQL    │
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
| 数据连接 | `/admin/integration/connectors` | Connector 配置、凭据、Computer Use 任务 |
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

### Data Connector（Computer Use → SQL → Ontology）

从只有 Web 界面的外部系统采集数据，先写入 SQL 暂存区，再同步到本体。

#### LLM Computer Use 自动采集（推荐）

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

- **立即采集** — 调用已配置 LLM + Playwright 执行采集
- **演示采集 (Mock)** — 使用样例 JSON，适合本机演示
- **启用定时采集** — 设置 `interval_sec`，配合 `ontology-connector daemon` 无人值守运行

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

```
src/ontology_platform/
├── ontology/          # 本体核心（schema, service, store/）
├── connector/         # Data Connector（Computer Use → SQL → sync）
├── integrations/      # Channel Adapter（IM / 邮件 / 跟催）
├── agent/             # LangGraph（graph, nodes, planner, tools）
├── governance/        # 审计日志 + RBAC 策略
├── platform.py        # AgentPlatform 入口
├── apps/prototype.py  # 样机管理应用
├── admin/             # 本体管理 Web UI（SPA、Excel 导入）
└── chat/              # Chainlit 辅助
chainlit_app.py        # Chainlit 入口
langgraph_studio.py    # LangGraph Studio 入口
examples/              # Ontology YAML + Connector + 采集样例
ARCHITECTURE.md        # 模式 A 架构文档
```

## 测试

```bash
pytest   # 含 connector 测试
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
- [x] Data Connector（Computer Use → SQL → Ontology）
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
