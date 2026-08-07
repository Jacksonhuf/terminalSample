# Ontology Agent Platform

基于 **Ontology（本体）** 和 **LangGraph** 的最小智能体搭建平台。参考 Palantir Foundry 的 Ontology 思路，将业务数据建模为可操作的对象、关系和动作，再通过 LangGraph 编排智能体工作流。

> 样机管理等具体业务场景是本平台之上的**应用层**，本仓库只提供平台核心能力。

## 架构

```
┌─────────────────────────────────────────────┐
│  AgentPlatform (应用入口)                    │
│  chat() / register_action_handler()         │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│  LangGraph Agent                             │
│  router → planner → executor → respond       │
└──────────────────┬──────────────────────────┘
                   │ tools
┌──────────────────▼──────────────────────────┐
│  OntologyService                             │
│  objects / links / actions / schema          │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│  OntologyRegistry + YAML Schema              │
│  ObjectType / Link / Action definitions      │
└─────────────────────────────────────────────┘
```

## 核心概念

| 概念 | 说明 |
|------|------|
| **ObjectType** | 业务对象类型（如 Person、Project） |
| **Property** | 对象属性，支持 string/integer/enum 等 |
| **Link** | 对象间关系（如 Person → works_on → Project） |
| **Action** | 可执行业务动作，支持审批门禁 |
| **LangGraph** | 编排 router/planner/executor/respond 节点 |

## 快速开始

### 安装

```bash
pip install -e ".[dev]"
```

### 运行 Demo

```bash
# 平台 Demo（Person/Project）
ontology-platform --seed --query "查询所有 Person"

# 样机管理应用
ontology-platform --app prototype --seed --query "查询所有可用样机"
```

### 本体管理界面 & 可视化

通过 Web UI 管理本体定义（增删改对象类型、关系、动作），并可视化本体图谱：

```bash
# 启动管理界面（默认加载 examples/ 目录下的 YAML）
ontology-admin --port 8080

# 指定本体目录
ontology-admin --dir ./my_ontologies --port 8080
```

浏览器访问：

| 页面 | 地址 | 功能 |
|------|------|------|
| 本体列表 | http://localhost:8080/ | 查看所有本体、新建 |
| 编辑器 | http://localhost:8080/editor | 编辑对象类型/关系/动作，保存为 YAML |
| 可视化 | http://localhost:8080/visualize | 交互式图谱（对象、关系、动作） |

在编辑器中修改后点击「保存」，会直接写入 YAML 文件，智能体下次加载时即生效。

### Chainlit 对话界面（智能体前端）

通过 Chainlit 与 Ontology 智能体对话，支持步骤展示和审批按钮：

```bash
pip install -e ".[chat]"
chainlit run chainlit_app.py
```

浏览器打开 http://localhost:8000，可尝试：

- `查询所有可用样机`
- `SN-2024-001 归属哪个项目`
- `预约 SN-2024-003`（会弹出批准/拒绝按钮）

环境变量：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ONTOLOGY_APP` | `prototype` | `prototype` 或 `demo` |
| `ONTOLOGY_STORE_PATH` | — | SQLite 持久化路径 |
| `ONTOLOGY_SEED` | `true` | 启动时注入示例数据 |

### 样机管理应用（第一个垂直应用）

```python
from ontology_platform import PrototypeApp

app = PrototypeApp.create()
app.seed()
print(app.chat("查询 X100 型号样机"))
print(app.chat("SN-2024-001 归属哪个项目"))
print(app.chat("预约 SN-2024-003"))  # 触发审批提示
```

样机 Ontology 定义见 `examples/prototype_ontology.yaml`：

| 对象 | 说明 |
|------|------|
| Prototype | 样机（序列号、型号、状态） |
| Person | 人员 |
| Project | 项目 |
| Location | 库位 |

| 动作 | 说明 |
|------|------|
| ReservePrototype | 预约（需审批） |
| CheckoutPrototype | 领用（需审批） |
| ReturnPrototype | 归还 |
| RetirePrototype | 报废（需审批） |

### 定义自己的 Ontology

在 YAML 中声明对象、关系和动作：

```yaml
# examples/demo_ontology.yaml
name: demo
object_types:
  - name: Person
    properties:
      - { name: id, type: string, required: true }
      - { name: name, type: string, required: true }
links:
  - { name: works_on, source_type: Person, target_type: Project }
actions:
  - name: AssignToProject
    target_type: Person
    requires_approval: true
    parameters:
      - { name: project_id, type: string, required: true }
```

### 在代码中使用

```python
from ontology_platform import AgentPlatform

platform = AgentPlatform.from_yaml("examples/demo_ontology.yaml")
platform.seed_demo_data()

# 注册自定义动作处理器
def my_handler(service, target, params):
  ...

platform.register_action_handler("MyAction", my_handler)

# 对话
print(platform.chat("查询所有 Person"))
```

## 项目结构

```
src/ontology_platform/
├── ontology/          # 本体核心
│   ├── schema.py      # ObjectType / Link / Action 定义
│   ├── store.py       # 内存存储
│   ├── registry.py    # 本体注册 & YAML 加载
│   └── service.py     # 运行时 CRUD / 查询 / 动作执行
├── agent/             # LangGraph 智能体
│   ├── state.py       # 图状态
│   ├── nodes.py       # router / planner / executor / respond
│   ├── tools.py       # Ontology → LangChain Tools
│   └── graph.py       # 图构建
├── platform.py        # 平台入口
├── apps/
│   └── prototype.py   # 样机管理应用
├── admin/             # 本体管理 Web UI
│   ├── manager.py     # YAML CRUD
│   ├── server.py      # FastAPI 后端
│   └── static/        # 前端页面
└── cli.py             # 命令行工具
examples/
├── demo_ontology.yaml       # 平台 Demo
└── prototype_ontology.yaml  # 样机管理 Ontology
tests/
├── test_platform.py
└── test_prototype.py
```

## 扩展路线

1. **持久化** — 将 `OntologyStore` 替换为 PostgreSQL / Neo4j
2. **LLM 集成** — 在 planner 节点接入 LLM，替代规则路由
3. **审批流** — LangGraph `interrupt` 实现 Human-in-the-loop
4. **多本体** — 支持同时注册多个 ontology，按应用切换
5. **应用层** — 在此平台上构建样机管理等垂直智能体

## 测试

```bash
pytest
```
