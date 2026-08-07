"""FastAPI server for ontology management and visualization."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ontology_platform.admin.manager import OntologyManager
from ontology_platform.ontology.schema import (
    ActionDef,
    LinkDef,
    ObjectTypeDef,
    OntologyDef,
)

STATIC_DIR = Path(__file__).parent / "static"


class CreateOntologyRequest(BaseModel):
    name: str
    description: str = ""
    version: str = "1.0"


class ResolveApprovalRequest(BaseModel):
    approved: bool = True
    resolver_id: str = "admin"
    resolver_roles: list[str] = Field(default_factory=lambda: ["admin"])


def create_app(
    ontology_dir: str | Path | None = None,
    audit_path: str | Path | None = None,
    integrations_db_path: str | Path | None = None,
    ontology_yaml_path: str | Path | None = None,
    ontology_db_path: str | Path | None = None,
    store_path: str | Path | None = None,
    database_url: str | None = None,
) -> FastAPI:
    base_dir = Path(ontology_dir) if ontology_dir else Path(__file__).parent.parent.parent.parent / "examples"
    manager = OntologyManager(base_dir)
    from ontology_platform.governance.approval_store import ApprovalStore
    from ontology_platform.governance.audit import AuditLogger
    from ontology_platform.integrations.factory import build_notification_service
    from ontology_platform.integrations.message_log import MessageLogStore
    from ontology_platform.integrations.outreach.store import OutreachStore
    from ontology_platform.integrations.outreach.worker import process_due_tasks
    from ontology_platform.agent.config import AgentConfig
    from ontology_platform.ontology.registry import OntologyRegistry
    from ontology_platform.ontology.service import OntologyService
    from ontology_platform.ontology.store.sqlite import SQLiteStore
    from ontology_platform.runtime import build_runtime_platform

    resolved_store_path = store_path or audit_path
    audit_logger = AuditLogger(resolved_store_path) if resolved_store_path else None
    approval_store = ApprovalStore(resolved_store_path) if resolved_store_path else None
    integrations_path = integrations_db_path or resolved_store_path
    message_log = MessageLogStore(integrations_path) if integrations_path else None
    outreach_store = OutreachStore(integrations_path) if integrations_path else None
    yaml_path = Path(ontology_yaml_path) if ontology_yaml_path else base_dir / "prototype_ontology.yaml"
    obj_db_path = Path(ontology_db_path) if ontology_db_path else None
    runtime_platform = {"instance": None}

    def _get_runtime_platform():
        if runtime_platform["instance"] is None and yaml_path.exists() and (resolved_store_path or database_url):
            runtime_platform["instance"] = build_runtime_platform(
                ontology_yaml=yaml_path,
                store_path=resolved_store_path,
                database_url=database_url,
                audit_path=resolved_store_path,
                integrations_db_path=integrations_path,
            )
        return runtime_platform["instance"]

    app = FastAPI(
        title="Ontology Admin",
        description="本体定义管理与可视化",
        version="0.1.0",
    )

    # --- API ---

    @app.get("/api/audit-logs")
    def audit_logs(action_name: str | None = None, user_id: str | None = None, limit: int = 100):
        if audit_logger is None:
            return {"logs": [], "message": "未配置审计日志路径", "configured": False}
        logs = audit_logger.query(action_name=action_name, user_id=user_id, limit=limit)
        return {"logs": [log.model_dump() for log in logs], "count": len(logs), "configured": True}

    @app.get("/api/message-logs")
    def message_logs(
        object_type: str | None = None,
        object_id: str | None = None,
        limit: int = 100,
    ):
        if message_log is None:
            return {"logs": [], "message": "未配置 integrations 数据库路径", "configured": False}
        logs = message_log.query(object_type=object_type, object_id=object_id, limit=limit)
        return {"logs": [log.model_dump() for log in logs], "count": len(logs), "configured": True}

    @app.get("/api/outreach-tasks")
    def outreach_tasks(
        status: str | None = None,
        object_type: str | None = None,
        object_id: str | None = None,
        limit: int = 100,
    ):
        if outreach_store is None:
            return {"tasks": [], "message": "未配置 integrations 数据库路径", "configured": False}
        tasks = outreach_store.list_tasks(
            status=status,
            object_type=object_type,
            object_id=object_id,
            limit=limit,
        )
        return {
            "tasks": [t.model_dump(mode="json") for t in tasks],
            "count": len(tasks),
            "configured": True,
        }

    @app.post("/api/outreach/run")
    def run_outreach_worker():
        if integrations_path is None:
            raise HTTPException(400, "未配置 integrations 数据库路径")
        if not yaml_path.exists():
            raise HTTPException(400, f"Ontology YAML 不存在: {yaml_path}")
        registry = OntologyRegistry.from_yaml(yaml_path)
        ontology_name = registry.list_ontologies()[0]
        db = obj_db_path or Path(integrations_path).parent / f"{ontology_name}.db"
        config = AgentConfig(store_path=str(integrations_path), integrations_db_path=str(integrations_path))
        notification = build_notification_service(config)
        service = OntologyService(registry, ontology_name, store=SQLiteStore(str(db)))
        result = process_due_tasks(notification, service)
        return result

    @app.get("/api/operations/status")
    def operations_status():
        return {
            "audit_configured": audit_logger is not None,
            "integrations_configured": integrations_path is not None,
            "approvals_configured": approval_store is not None,
            "runtime_configured": bool(resolved_store_path or database_url),
            "audit_path": str(resolved_store_path) if resolved_store_path else "",
            "integrations_path": str(integrations_path) if integrations_path else "",
            "database_url": database_url or "",
            "ontology_yaml": str(yaml_path),
            "ontology_db": str(obj_db_path or ""),
        }

    @app.get("/api/approvals")
    def list_approvals(status: str | None = None, limit: int = 100):
        if approval_store is None:
            return {"requests": [], "message": "未配置审批存储路径", "configured": False}
        requests = approval_store.list_requests(status=status, limit=limit)
        return {
            "requests": [r.model_dump() for r in requests],
            "count": len(requests),
            "configured": True,
        }

    @app.post("/api/approvals/{request_id}/resolve")
    def resolve_approval(request_id: str, body: ResolveApprovalRequest):
        if approval_store is None:
            raise HTTPException(400, "未配置审批存储路径")
        request = approval_store.get(request_id)
        if request is None:
            raise HTTPException(404, f"Approval request not found: {request_id}")
        if request.status != "pending":
            raise HTTPException(400, f"Approval request already {request.status}")

        platform = _get_runtime_platform()
        if platform is None:
            raise HTTPException(400, "未配置运行时平台（需要 store-path 或 database-url）")

        snapshot = platform.graph.get_state({"configurable": {"thread_id": request.thread_id}})
        if not snapshot.next:
            approval_store.resolve(
                request_id,
                approved=body.approved,
                resolver_id=body.resolver_id,
                resolver_roles=body.resolver_roles,
            )
            return {
                "message": "审批记录已更新（无活动 interrupt，可能已在其他入口处理）",
                "request_id": request_id,
                "status": "approved" if body.approved else "rejected",
            }

        result = platform.resume(
            approved=body.approved,
            thread_id=request.thread_id,
            user_id=body.resolver_id,
            roles=body.resolver_roles,
        )
        return {
            "request_id": request_id,
            "status": "approved" if body.approved else "rejected",
            "response": result.response,
            "interrupted": result.interrupted,
        }

    @app.get("/api/ontologies")
    def list_ontologies():
        return {"ontologies": manager.list_ontologies(), "directory": str(manager.directory)}

    @app.get("/api/ontologies/{name}")
    def get_ontology(name: str):
        try:
            ontology = manager.load(name)
            return ontology.model_dump()
        except FileNotFoundError:
            raise HTTPException(404, f"Ontology not found: {name}")

    @app.post("/api/ontologies")
    def create_ontology(req: CreateOntologyRequest):
        try:
            ontology = OntologyDef(name=req.name, description=req.description, version=req.version)
            path = manager.create(ontology)
            return {"message": "created", "path": str(path), "ontology": ontology.model_dump()}
        except ValueError as e:
            raise HTTPException(409, str(e))

    @app.put("/api/ontologies/{name}")
    def update_ontology(name: str, data: dict):
        try:
            ontology = OntologyDef.model_validate(data)
            if ontology.name != name:
                raise HTTPException(400, "Ontology name in body must match URL")
            path = manager.save(ontology)
            return {"message": "saved", "path": str(path), "ontology": ontology.model_dump()}
        except Exception as e:
            raise HTTPException(400, str(e))

    @app.delete("/api/ontologies/{name}")
    def delete_ontology(name: str):
        if not manager.delete(name):
            raise HTTPException(404, f"Ontology not found: {name}")
        return {"message": "deleted", "name": name}

    @app.get("/api/ontologies/{name}/graph")
    def get_graph(name: str):
        try:
            return manager.to_graph(name)
        except FileNotFoundError:
            raise HTTPException(404, f"Ontology not found: {name}")

    # Object type CRUD
    @app.post("/api/ontologies/{name}/object-types")
    def add_object_type(name: str, obj_type: ObjectTypeDef):
        ontology = _load_or_404(manager, name)
        if ontology.get_object_type(obj_type.name):
            raise HTTPException(409, f"Object type already exists: {obj_type.name}")
        ontology.object_types.append(obj_type)
        manager.save(ontology)
        return obj_type.model_dump()

    @app.put("/api/ontologies/{name}/object-types/{type_name}")
    def update_object_type(name: str, type_name: str, obj_type: ObjectTypeDef):
        ontology = _load_or_404(manager, name)
        idx = _find_index(ontology.object_types, type_name, "name")
        if idx is None:
            raise HTTPException(404, f"Object type not found: {type_name}")
        ontology.object_types[idx] = obj_type
        manager.save(ontology)
        return obj_type.model_dump()

    @app.delete("/api/ontologies/{name}/object-types/{type_name}")
    def delete_object_type(name: str, type_name: str):
        ontology = _load_or_404(manager, name)
        idx = _find_index(ontology.object_types, type_name, "name")
        if idx is None:
            raise HTTPException(404, f"Object type not found: {type_name}")
        ontology.object_types.pop(idx)
        manager.save(ontology)
        return {"message": "deleted", "name": type_name}

    # Link CRUD
    @app.post("/api/ontologies/{name}/links")
    def add_link(name: str, link: LinkDef):
        ontology = _load_or_404(manager, name)
        if ontology.get_link(link.name):
            raise HTTPException(409, f"Link already exists: {link.name}")
        ontology.links.append(link)
        manager.save(ontology)
        return link.model_dump()

    @app.delete("/api/ontologies/{name}/links/{link_name}")
    def delete_link(name: str, link_name: str):
        ontology = _load_or_404(manager, name)
        idx = _find_index(ontology.links, link_name, "name")
        if idx is None:
            raise HTTPException(404, f"Link not found: {link_name}")
        ontology.links.pop(idx)
        manager.save(ontology)
        return {"message": "deleted", "name": link_name}

    # Action CRUD
    @app.post("/api/ontologies/{name}/actions")
    def add_action(name: str, action: ActionDef):
        ontology = _load_or_404(manager, name)
        if ontology.get_action(action.name):
            raise HTTPException(409, f"Action already exists: {action.name}")
        ontology.actions.append(action)
        manager.save(ontology)
        return action.model_dump()

    @app.delete("/api/ontologies/{name}/actions/{action_name}")
    def delete_action(name: str, action_name: str):
        ontology = _load_or_404(manager, name)
        idx = _find_index(ontology.actions, action_name, "name")
        if idx is None:
            raise HTTPException(404, f"Action not found: {action_name}")
        ontology.actions.pop(idx)
        manager.save(ontology)
        return {"message": "deleted", "name": action_name}

    # --- Static UI pages ---

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/editor")
    def editor_page():
        return FileResponse(STATIC_DIR / "editor.html")

    @app.get("/visualize")
    def visualize_page():
        return FileResponse(STATIC_DIR / "visualize.html")

    @app.get("/operations")
    def operations_page():
        return FileResponse(STATIC_DIR / "operations.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    return app


def _load_or_404(manager: OntologyManager, name: str) -> OntologyDef:
    try:
        return manager.load(name)
    except FileNotFoundError:
        raise HTTPException(404, f"Ontology not found: {name}")


def _find_index(items: list, name: str, attr: str) -> int | None:
    for i, item in enumerate(items):
        if getattr(item, attr) == name:
            return i
    return None
