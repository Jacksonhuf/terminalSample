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

### 安装

```bash
pip install -e ".[dev,chat,studio]"
```

可选 extras：

| Extra | 用途 |
|-------|------|
| `dev` | pytest |
| `chat` | Chainlit 对话界面 |
| `studio` | LangGraph Studio 调试 |

### 运行 Demo（命令行）

```bash
# 平台 Demo（Person/Project）
ontology-platform --seed --query "查询所有 Person"

# 样机管理应用
ontology-platform --app prototype --seed --query "查询所有可用样机"
```

### Chainlit 对话界面（智能体前端）

```bash
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

```bash
ontology-admin --port 8080
# 指定目录：ontology-admin --dir ./my_ontologies --port 8080
```

| 页面 | 地址 | 功能 |
|------|------|------|
| 本体列表 | http://localhost:8080/ | 查看/新建本体 |
| 编辑器 | http://localhost:8080/editor | 编辑对象/关系/动作，保存 YAML |
| 可视化 | http://localhost:8080/visualize | 交互式本体图谱 |
| 审计日志 | http://localhost:8080/api/audit-logs | 需 `--store-path` 配置数据库 |
| 运营中心 | http://localhost:8080/operations | 审计 / 消息 / 跟催任务可视化 |

启动时指定数据路径以启用运营功能：

```bash
ontology-admin --port 8080 --store-path ./data/platform.db
```

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
print(app.chat("预约 SN-2024-003"))
```

详见 `examples/prototype_ontology.yaml`（Prototype / Person / Project / Location + 8 个动作，含 IM/邮件通知）。

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

从只有 Web 界面的外部系统采集数据，先写入 SQL 暂存区，再同步到本体：

```bash
# 1. 生成 Computer Use 采集任务（含 run_id 与操作说明）
ontology-connector task prototype_erp

# 2. Computer Use 完成后，将采集 JSON 入库
ontology-connector ingest examples/captures/prototype_erp_sample.json

# 3. 映射同步到 Ontology
ontology-connector sync prototype_erp

# 查看运行状态
ontology-connector status prototype_erp
ontology-connector list
```

Connector 定义见 `examples/connectors/`，采集样例见 `examples/captures/`。完整说明见 [ARCHITECTURE.md](ARCHITECTURE.md#5-数据层data-connectorcomputer-use--sql--ontology)。

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
├── admin/             # 本体管理 Web UI
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

## 扩展路线

- [x] Outbound Channels（IM / 邮件 / 跟催）
- [x] Data Connector（Computer Use → SQL → Ontology）
- [x] 审计日志 / 消息 / 跟催 admin 运营中心
- [x] outreach 守护进程 (`ontology-outreach daemon`)
- [x] Chainlit 用户身份与 RBAC 对接（含角色映射）
- [ ] PostgreSQL / Neo4j 持久化
- [ ] LDAP / SSO 用户集成
- [ ] 自研 Logic 可视化编辑器（长期）
- [x] LLM Planner
- [x] 审批流（LangGraph interrupt）
- [x] SQLite 持久化
- [x] Chainlit 对话前端
- [x] 本体管理 & 可视化 UI
- [x] Action 审计 + RBAC
