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
# 交互模式
ontology-platform --seed

# 单次查询
ontology-platform --seed --query "查询所有 Person"
```

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
└── cli.py             # 命令行工具
examples/
└── demo_ontology.yaml # 示例本体
tests/
└── test_platform.py
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
