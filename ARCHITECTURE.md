# 架构说明 — 模式 A（纯自建）

本文档定义本平台的架构决策、与 Palantir 的对应关系，以及治理与调试方案。

## 1. 融合模式：模式 A（纯自建）

**决策**：完全自建 Ontology + 编排 + 治理栈，不依赖 Palantir 商业产品。

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 4: 体验层                                              │
│   Chainlit (对话)  |  ontology-admin (本体管理/可视化)        │
├─────────────────────────────────────────────────────────────┤
│ Layer 3: 编排层 — LangGraph                                  │
│   plan → execute → approval → respond                        │
│   ≈ Palantir AIP Logic + AIP Agent                          │
├─────────────────────────────────────────────────────────────┤
│ Layer 2: 语义层 — Ontology Platform                          │
│   Object / Link / Action  ≈ Palantir Ontology               │
├─────────────────────────────────────────────────────────────┤
│ Layer 2.5: 治理层 — Governance（新增）                        │
│   RBAC 权限  |  Action 审计日志                              │
├─────────────────────────────────────────────────────────────┤
│ Layer 1: 数据层                                              │
│   Data Connector (Computer Use → SQL)  |  Ontology Store    │
└─────────────────────────────────────────────────────────────┘
```

### 与 Palantir 能力映射

| Palantir | 自建实现 | 状态 |
|----------|---------|------|
| Ontology (Object/Link/Action) | YAML + OntologyService | ✅ |
| AIP Logic (工作流编排) | LangGraph | ✅ |
| AIP Agent (对话) | Chainlit + AgentPlatform | ✅ |
| Human Review | LangGraph interrupt | ✅ |
| Action 审计 | AuditLogger | ✅ |
| Action 权限 | PolicyEngine (RBAC) | ✅ |
| Workshop (应用 UI) | ontology-admin | ✅ |
| Logic 可视化编辑器 | LangGraph Studio（调试） | ✅ 短期 |
| Data Connection / Pipeline | Data Connector (Computer Use → SQL) | ✅ |

---

## 2. 编排可视化：LangGraph Studio（短期）

开发阶段使用 **LangGraph Studio** 调试编排图，不做自研 Logic 编辑器。

### 启动方式

```bash
pip install -e ".[studio]"
langgraph dev
```

浏览器打开 LangGraph Studio，可：

- 可视化 `plan → execute → approval → respond` 全流程
- 单步调试每个节点
- 检查 State 变化（intent、plan、ontology_results）
- 测试 interrupt 审批分支

入口文件：`langgraph_studio.py`（导出 `graph` 变量）  
配置文件：`langgraph.json`

---

## 3. 治理层：Action 审计日志

每次 `execute_action` 调用自动记录：

| 字段 | 说明 |
|------|------|
| timestamp | UTC 时间 |
| user_id | 执行人 |
| roles | 当时角色 |
| action_name | 动作名 |
| target_id | 目标对象 |
| parameters | 参数 |
| status | success / failed / denied / approval_required |
| approved | 是否经审批 |

### 查询审计日志

```python
platform.get_audit_logs(action_name="ReservePrototype", limit=50)
```

```bash
# Admin API（需配置 audit_path）
GET /api/audit-logs?action_name=ReservePrototype
```

审计日志存储在 SQLite（与 `store_path` 共用或独立 `audit_path`）。

---

## 4. 治理层：权限模型（RBAC）

### 内置角色

| 角色 | 权限 |
|------|------|
| **admin** | 查询 + 执行所有动作 + 审批 |
| **operator** | 查询 + 执行（非 admin 专属动作） |
| **viewer** | 仅查询，不可执行写操作 |

### Action 级策略（在 Ontology YAML 中定义）

```yaml
actions:
  - name: ReservePrototype
    allowed_roles: [operator, admin]    # 谁可以发起
    approver_roles: [admin]             # 谁可以审批
    requires_approval: true
```

### 代码中指定用户上下文

```python
platform.chat("预约 SN-2024-001", user_id="zhangsan", roles=["operator"])
platform.resume(approved=True, user_id="admin", roles=["admin"])
```

### 权限检查流程

```
execute_action
  → viewer? → denied
  → allowed_roles 检查 → denied
  → requires_approval + approved? → approver_roles 检查
  → 执行 handler
  → 写入审计日志
```

---

## 5. 数据层：Data Connector（Computer Use → SQL → Ontology）

当外部系统没有开放 API、只有 Web 界面时，使用 **Computer Use** 代理模拟人工操作采集数据，先落地 SQL 暂存区，再映射同步到 Ontology。

### 数据流

```
Connector YAML  →  Computer Use Agent  →  Capture JSON
       ↓                                      ↓
  task 指令                            ingest → SQLite staging
                                              ↓
                                    sync → OntologyService
```

### 1. 定义 Connector（YAML）

`examples/connectors/prototype_erp.yaml`：

- `mode: computer_use` — 采集模式
- `source_url` — 目标 Web 地址
- `capture_instructions` — 给 Computer Use 的操作说明
- `record_mappings` — 原始记录类型 → Ontology 对象类型字段映射

### 2. 生成采集任务

```bash
ontology-connector task prototype_erp
# 或 JSON 输出，供 Cursor Computer Use 子代理消费
ontology-connector task prototype_erp --json
```

返回 `run_id`、操作说明和期望的 `CaptureBatch` JSON 格式。

### 3. Computer Use 提交采集结果

代理完成页面操作后，将数据保存为 JSON（见 `examples/captures/prototype_erp_sample.json`），再入库：

```bash
ontology-connector ingest examples/captures/prototype_erp_sample.json
```

### 4. 同步到 Ontology

```bash
ontology-connector sync prototype_erp
ontology-connector status prototype_erp
```

### Python API

```python
from pathlib import Path
from ontology_platform.connector import ConnectorManager, ConnectorStore, CaptureBatch
from ontology_platform.ontology.registry import OntologyRegistry
from ontology_platform.ontology.service import OntologyService
from ontology_platform.ontology.store.sqlite import SQLiteStore

store = ConnectorStore("./data/connector.db")
registry = OntologyRegistry.from_yaml("examples/prototype_ontology.yaml")
svc = OntologyService(registry, "prototype", store=SQLiteStore("./data/prototype.db"))
mgr = ConnectorManager("examples/connectors", store, svc)

task = mgr.get_computer_use_task("prototype_erp")
batch = CaptureBatch.model_validate(capture_json)
mgr.ingest_batch(batch)
mgr.sync_to_ontology("prototype_erp")
```

### SQL 表结构

| 表 | 用途 |
|----|------|
| `connector_runs` | 每次采集运行元数据 |
| `connector_staged_records` | 原始记录暂存（含 sync 状态） |

---

## 6. 前端分工（模式 A）

| 组件 | 端口 | 职责 |
|------|------|------|
| ontology-admin | 8080 | 本体 CRUD + 图谱可视化 |
| Chainlit | 8000 | 智能体对话 + 审批按钮 |
| LangGraph Studio | 2024 | 编排调试（开发用） |

---

## 6. 后续演进

| 阶段 | 方向 |
|------|------|
| 短期 | LangGraph Studio 调试、审计日志查询 UI |
| 中期 | PostgreSQL、审批工作台、LDAP 用户集成 |
| 长期 | 自研 Logic 可视化编辑器（类 AIP Logic UI） |
