"""FastAPI server for ontology management and visualization."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ontology_platform.admin.manager import OntologyManager
from ontology_platform.admin.llm_api import SaveLlmProfileRequest, SaveProxyConfigRequest, proxy_to_dict
from ontology_platform.admin.connectors_api import (
    CreateCredentialRequest,
    RotatePasswordRequest,
    SaveConnectorRequest,
    UpdateCredentialRequest,
    build_connector_manager,
    connector_to_public,
    save_connector_from_request,
)
from ontology_platform.admin.mapping_api import (
    SaveMappingProfileRequest,
    SyncMappingRequest,
    build_mapping_service,
    build_mapping_store,
    get_ontology_object_types,
    profile_to_dict,
    resolve_ontology_service,
)
from ontology_platform.mapping.schema import FieldRule
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


class BatchResolveApprovalRequest(BaseModel):
    request_ids: list[str] = Field(default_factory=list)
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
    connectors_dir: str | Path | None = None,
    credential_db_path: str | Path | None = None,
    connector_db_path: str | Path | None = None,
    mapping_db_path: str | Path | None = None,
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
    from ontology_platform.connector.credential_store import CredentialStore
    from ontology_platform.governance.audit import AuditLogEntry

    from ontology_platform.llm.store import LlmConfigStore
    from ontology_platform.llm.factory import test_llm_connection

    resolved_store_path = store_path or audit_path
    audit_logger = AuditLogger(resolved_store_path) if resolved_store_path else None
    approval_store = ApprovalStore(resolved_store_path) if resolved_store_path else None
    integrations_path = integrations_db_path or resolved_store_path
    message_log = MessageLogStore(integrations_path) if integrations_path else None
    outreach_store = OutreachStore(integrations_path) if integrations_path else None
    yaml_path = Path(ontology_yaml_path) if ontology_yaml_path else base_dir / "prototype_ontology.yaml"
    obj_db_path = Path(ontology_db_path) if ontology_db_path else None
    connectors_path = Path(connectors_dir) if connectors_dir else base_dir / "connectors"
    cred_db = credential_db_path or resolved_store_path
    credential_store = CredentialStore(cred_db) if cred_db else None
    llm_store = LlmConfigStore(cred_db) if cred_db else None
    mapping_db = Path(mapping_db_path) if mapping_db_path else (
        Path(connector_db_path) if connector_db_path else connectors_path.parent / "mapping.db"
    )
    mapping_store = build_mapping_store(mapping_db, connectors_path)
    connector_mgr = build_connector_manager(
        connectors_path,
        Path(connector_db_path) if connector_db_path else None,
        credential_store,
        mapping_store=mapping_store,
    )
    connector_store = connector_mgr.store
    mapping_service = build_mapping_service(mapping_store, connector_store)
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

    def _resolve_approval_request(request_id: str, body: ResolveApprovalRequest) -> dict:
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
            "prototype_configured": bool(
                yaml_path.exists() and (resolved_store_path or database_url)
            ),
            "connectors_configured": connectors_path.exists(),
            "credentials_configured": credential_store is not None,
            "llm_configured": llm_store is not None,
            "connectors_dir": str(connectors_path),
            "credential_db": str(cred_db) if cred_db else "",
            "audit_path": str(resolved_store_path) if resolved_store_path else "",
            "integrations_path": str(integrations_path) if integrations_path else "",
            "database_url": database_url or "",
            "ontology_yaml": str(yaml_path),
            "ontology_db": str(obj_db_path or ""),
            "mapping_db": str(mapping_db),
        }

    @app.get("/api/prototype/dashboard")
    def prototype_dashboard():
        from ontology_platform.apps.prototype_analytics import build_dashboard

        platform = _get_runtime_platform()
        if platform is None:
            return {"configured": False, "message": "未配置运行时平台（需要 store-path 或 database-url）"}
        dashboard = build_dashboard(platform.get_service())
        return {"configured": True, **dashboard}

    @app.post("/api/prototype/seed")
    def prototype_seed():
        from ontology_platform.apps.prototype import PrototypeApp

        if not yaml_path.exists():
            raise HTTPException(400, f"Ontology YAML 不存在: {yaml_path}")
        config = AgentConfig(
            store_path=str(resolved_store_path) if resolved_store_path else None,
            database_url=database_url,
            audit_path=str(resolved_store_path) if resolved_store_path else None,
            integrations_db_path=str(integrations_path) if integrations_path else None,
            enable_governance=True,
            enable_approval_flow=True,
        )
        app_instance = PrototypeApp.create(ontology_path=yaml_path, config=config)
        had_data = app_instance.service.get_object("Person", "P-001") is not None
        app_instance.seed()
        runtime_platform["instance"] = app_instance.platform
        return {
            "seeded": not had_data,
            "message": "演示数据已存在" if had_data else "已写入演示数据",
            "dashboard": app_instance.get_dashboard(),
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
        return _resolve_approval_request(request_id, body)

    @app.post("/api/approvals/batch-resolve")
    def batch_resolve_approval(body: BatchResolveApprovalRequest):
        if not body.request_ids:
            raise HTTPException(400, "request_ids 不能为空")
        succeeded: list[dict] = []
        failed: list[dict] = []
        for request_id in body.request_ids:
            try:
                result = _resolve_approval_request(request_id, body)
                succeeded.append(result)
            except HTTPException as exc:
                failed.append({"request_id": request_id, "error": str(exc.detail)})
            except Exception as exc:
                failed.append({"request_id": request_id, "error": str(exc)})
        return {
            "total": len(body.request_ids),
            "succeeded": succeeded,
            "failed": failed,
            "approved": body.approved,
        }

    @app.get("/api/credentials")
    def list_credentials():
        if credential_store is None:
            return {"credentials": [], "configured": False, "message": "未配置凭据存储路径"}
        items = credential_store.list_public()
        return {"credentials": [c.model_dump() for c in items], "count": len(items), "configured": True}

    @app.post("/api/credentials")
    def create_credential(req: CreateCredentialRequest = Body()):
        if credential_store is None:
            raise HTTPException(400, "未配置凭据存储路径")
        try:
            cred = credential_store.create(
                name=req.name,
                username=req.username,
                password=req.password,
                credential_id=req.credential_id or None,
                login_url=req.login_url,
                notes=req.notes,
            )
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        if audit_logger:
            audit_logger.log(
                AuditLogEntry(
                    user_id="admin-ui",
                    action_name="CredentialCreated",
                    target_id=cred.id,
                    status="success",
                    success=True,
                    message=f"创建凭据 {cred.name}",
                )
            )
        return cred.model_dump()

    @app.put("/api/credentials/{credential_id}")
    def update_credential(credential_id: str, req: UpdateCredentialRequest = Body()):
        if credential_store is None:
            raise HTTPException(400, "未配置凭据存储路径")
        cred = credential_store.update(
            credential_id,
            name=req.name,
            username=req.username,
            login_url=req.login_url,
            notes=req.notes,
        )
        if cred is None:
            raise HTTPException(404, f"Credential not found: {credential_id}")
        return cred.model_dump()

    @app.put("/api/credentials/{credential_id}/password")
    def rotate_credential_password(credential_id: str, req: RotatePasswordRequest = Body()):
        if credential_store is None:
            raise HTTPException(400, "未配置凭据存储路径")
        cred = credential_store.rotate_password(credential_id, req.password)
        if cred is None:
            raise HTTPException(404, f"Credential not found: {credential_id}")
        if audit_logger:
            audit_logger.log(
                AuditLogEntry(
                    user_id="admin-ui",
                    action_name="CredentialPasswordRotated",
                    target_id=credential_id,
                    status="success",
                    success=True,
                    message="轮换凭据密码",
                )
            )
        return cred.model_dump()

    @app.delete("/api/credentials/{credential_id}")
    def delete_credential(credential_id: str):
        if credential_store is None:
            raise HTTPException(400, "未配置凭据存储路径")
        refs = connector_mgr.find_credential_references(credential_id)
        if refs:
            raise HTTPException(409, f"凭据仍被连接器引用: {', '.join(refs)}")
        if not credential_store.delete(credential_id):
            raise HTTPException(404, f"Credential not found: {credential_id}")
        return {"message": "deleted", "id": credential_id}

    @app.get("/api/connectors")
    def list_connectors_api():
        connectors = connector_mgr.list_connector_defs()
        return {
            "connectors": [connector_to_public(c) for c in connectors],
            "count": len(connectors),
            "directory": str(connectors_path),
        }

    @app.get("/api/connectors/{name}")
    def get_connector_api(name: str):
        try:
            connector = connector_mgr.load_connector(name)
        except FileNotFoundError:
            raise HTTPException(404, f"Connector not found: {name}")
        return connector_to_public(connector)

    @app.put("/api/connectors/{name}")
    def save_connector_api(name: str, req: SaveConnectorRequest = Body()):
        if req.name != name:
            raise HTTPException(400, "Connector name in body must match URL")
        connector = save_connector_from_request(connector_mgr, req)
        return connector_to_public(connector)

    @app.post("/api/connectors")
    def create_connector_api(req: SaveConnectorRequest = Body()):
        try:
            connector_mgr.load_connector(req.name)
            raise HTTPException(409, f"Connector already exists: {req.name}")
        except FileNotFoundError:
            pass
        connector = save_connector_from_request(connector_mgr, req)
        return connector_to_public(connector)

    @app.delete("/api/connectors/{name}")
    def delete_connector_api(name: str):
        if not connector_mgr.delete_connector(name):
            raise HTTPException(404, f"Connector not found: {name}")
        return {"message": "deleted", "name": name}

    # --- Data mapping API ---

    @app.get("/api/mappings/staging")
    def list_staging_summary(connector: str | None = None):
        summaries = mapping_service.list_staging_summary(connector)
        return {"summaries": [s.model_dump() for s in summaries], "count": len(summaries)}

    @app.get("/api/mappings/staging/{connector}/{record_type}/samples")
    def get_staging_samples(connector: str, record_type: str, limit: int = 5):
        payloads = mapping_service.get_sample_payloads(connector, record_type, limit=limit)
        fields = connector_store.infer_fields(connector, record_type)
        return {"connector": connector, "record_type": record_type, "fields": fields, "samples": payloads}

    @app.get("/api/mappings/ontologies/{ontology_name}/object-types")
    def list_mapping_object_types(ontology_name: str):
        try:
            types = get_ontology_object_types(manager, ontology_name)
        except FileNotFoundError:
            raise HTTPException(404, f"Ontology not found: {ontology_name}")
        return {"ontology": ontology_name, "object_types": types}

    @app.get("/api/mappings/profiles")
    def list_mapping_profiles(
        connector: str | None = None,
        record_type: str | None = None,
        status: str | None = None,
    ):
        profiles = mapping_store.list_profiles(connector, record_type, status)
        return {"profiles": [profile_to_dict(p) for p in profiles], "count": len(profiles)}

    @app.get("/api/mappings/profiles/{profile_id}")
    def get_mapping_profile(profile_id: str):
        profile = mapping_store.get_profile(profile_id)
        if profile is None:
            raise HTTPException(404, f"Mapping profile not found: {profile_id}")
        return profile_to_dict(profile)

    @app.post("/api/mappings/profiles")
    def create_mapping_profile(req: SaveMappingProfileRequest = Body()):
        existing_active = mapping_store.get_active_profile(req.connector_name, req.record_type)
        if req.status == "active" and existing_active is not None:
            raise HTTPException(
                409,
                f"Active mapping already exists: {existing_active.name} ({existing_active.id})",
            )
        field_rules = [
            FieldRule(source=r.source, target=r.target, transform=r.transform)
            for r in req.field_rules
        ]
        profile = mapping_store.create_profile(
            name=req.name,
            connector_name=req.connector_name,
            record_type=req.record_type,
            ontology_name=req.ontology_name,
            object_type=req.object_type,
            id_field=req.id_field,
            source_id_field=req.source_id_field,
            field_rules=field_rules,
            status=req.status,
        )
        if req.status == "active":
            profile = mapping_store.activate_profile(profile.id)
        return profile_to_dict(profile)

    @app.put("/api/mappings/profiles/{profile_id}")
    def update_mapping_profile(profile_id: str, req: SaveMappingProfileRequest = Body()):
        profile = mapping_store.get_profile(profile_id)
        if profile is None:
            raise HTTPException(404, f"Mapping profile not found: {profile_id}")
        if req.status == "active":
            existing_active = mapping_store.get_active_profile(req.connector_name, req.record_type)
            if existing_active is not None and existing_active.id != profile_id:
                raise HTTPException(
                    409,
                    f"Active mapping already exists: {existing_active.name}",
                )
        profile.name = req.name
        profile.connector_name = req.connector_name
        profile.record_type = req.record_type
        profile.ontology_name = req.ontology_name
        profile.object_type = req.object_type
        profile.id_field = req.id_field
        profile.source_id_field = req.source_id_field
        profile.field_rules = [
            FieldRule(source=r.source, target=r.target, transform=r.transform)
            for r in req.field_rules
        ]
        profile.status = req.status
        profile = mapping_store.update_profile(profile)
        if req.status == "active":
            profile = mapping_store.activate_profile(profile.id)
        return profile_to_dict(profile)

    @app.post("/api/mappings/profiles/{profile_id}/activate")
    def activate_mapping_profile(profile_id: str):
        try:
            profile = mapping_store.activate_profile(profile_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc))
        return profile_to_dict(profile)

    @app.delete("/api/mappings/profiles/{profile_id}")
    def delete_mapping_profile(profile_id: str):
        if not mapping_store.delete_profile(profile_id):
            raise HTTPException(404, f"Mapping profile not found: {profile_id}")
        return {"message": "deleted", "id": profile_id}

    @app.post("/api/mappings/profiles/{profile_id}/preview")
    def preview_mapping_profile(profile_id: str, limit: int = 10):
        profile = mapping_store.get_profile(profile_id)
        if profile is None:
            raise HTTPException(404, f"Mapping profile not found: {profile_id}")
        results = mapping_service.preview(profile, limit=limit)
        return {"profile_id": profile_id, "previews": [r.model_dump() for r in results]}

    @app.post("/api/mappings/profiles/{profile_id}/sync")
    def sync_mapping_profile(profile_id: str, body: SyncMappingRequest = Body(default=SyncMappingRequest())):
        profile = mapping_store.get_profile(profile_id)
        if profile is None:
            raise HTTPException(404, f"Mapping profile not found: {profile_id}")
        if not resolved_store_path and not database_url:
            raise HTTPException(400, "未配置 store-path 或 database-url，无法同步到 Ontology")
        try:
            ontology_service = resolve_ontology_service(
                manager,
                profile.ontology_name,
                resolved_store_path,
                database_url,
            )
        except FileNotFoundError:
            raise HTTPException(404, f"Ontology not found: {profile.ontology_name}")
        try:
            result = mapping_service.sync_profile(
                profile_id,
                ontology_service,
                resync=body.resync,
                run_id=body.run_id,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        runtime_platform["instance"] = None
        if audit_logger:
            audit_logger.log(
                AuditLogEntry(
                    user_id="admin-ui",
                    action_name="MappingSync",
                    target_id=profile_id,
                    status="success",
                    success=True,
                    message=f"同步 {result.get('synced', 0)} 条记录",
                )
            )
        return result

    @app.get("/api/mappings/sync-runs")
    def list_mapping_sync_runs(profile_id: str | None = None, limit: int = 50):
        runs = mapping_store.list_sync_runs(profile_id, limit=limit)
        return {"runs": [r.model_dump() for r in runs], "count": len(runs)}

    @app.post("/api/connectors/{name}/task")
    def generate_connector_task(name: str):
        try:
            task = connector_mgr.get_computer_use_task(name)
        except FileNotFoundError:
            raise HTTPException(404, f"Connector not found: {name}")
        if audit_logger:
            audit_logger.log(
                AuditLogEntry(
                    user_id="admin-ui",
                    action_name="ConnectorTaskGenerated",
                    target_id=name,
                    status="success",
                    success=True,
                    message=f"生成采集任务 run_id={task.get('run_id')}",
                )
            )
        return task

    @app.get("/api/llm/profiles")
    def list_llm_profiles():
        if llm_store is None:
            return {"profiles": [], "configured": False, "message": "未配置 LLM 存储路径"}
        profiles = llm_store.list_profiles(credential_store)
        return {"profiles": [p.model_dump() for p in profiles], "count": len(profiles), "configured": True}

    @app.get("/api/llm/profiles/{profile_id}")
    def get_llm_profile(profile_id: str):
        if llm_store is None:
            raise HTTPException(400, "未配置 LLM 存储路径")
        row = llm_store._get_row(profile_id)
        if row is None:
            raise HTTPException(404, f"LLM profile not found: {profile_id}")
        return llm_store._to_public(row, credential_store).model_dump()

    @app.post("/api/llm/profiles")
    def create_llm_profile(req: SaveLlmProfileRequest = Body()):
        if llm_store is None:
            raise HTTPException(400, "未配置 LLM 存储路径")
        try:
            profile = llm_store.create_profile(
                name=req.name,
                profile_id=req.id or None,
                provider=req.provider,
                base_url=req.base_url,
                model=req.model,
                api_key_ref=req.api_key_ref,
                planner_mode=req.planner_mode,
                proxy_mode=req.proxy_mode,
                temperature=req.temperature,
                timeout_sec=req.timeout_sec,
                max_tokens=req.max_tokens,
                enabled=req.enabled,
                is_default=req.is_default,
            )
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        runtime_platform["instance"] = None
        if audit_logger:
            audit_logger.log(
                AuditLogEntry(
                    user_id="admin-ui",
                    action_name="LlmProfileCreated",
                    target_id=profile.id,
                    status="success",
                    success=True,
                    message=f"创建 LLM 配置 {profile.name}",
                )
            )
        return profile.model_dump()

    @app.put("/api/llm/profiles/{profile_id}")
    def update_llm_profile(profile_id: str, req: SaveLlmProfileRequest = Body()):
        if llm_store is None:
            raise HTTPException(400, "未配置 LLM 存储路径")
        profile = llm_store.update_profile(
            profile_id,
            name=req.name,
            provider=req.provider,
            base_url=req.base_url,
            model=req.model,
            api_key_ref=req.api_key_ref,
            planner_mode=req.planner_mode,
            proxy_mode=req.proxy_mode,
            temperature=req.temperature,
            timeout_sec=req.timeout_sec,
            max_tokens=req.max_tokens,
            enabled=req.enabled,
            is_default=req.is_default,
        )
        if profile is None:
            raise HTTPException(404, f"LLM profile not found: {profile_id}")
        runtime_platform["instance"] = None
        return profile.model_dump()

    @app.delete("/api/llm/profiles/{profile_id}")
    def delete_llm_profile(profile_id: str):
        if llm_store is None:
            raise HTTPException(400, "未配置 LLM 存储路径")
        if not llm_store.delete_profile(profile_id):
            raise HTTPException(404, f"LLM profile not found: {profile_id}")
        runtime_platform["instance"] = None
        return {"message": "deleted", "id": profile_id}

    @app.post("/api/llm/profiles/{profile_id}/test")
    def test_llm_profile(profile_id: str):
        if llm_store is None:
            raise HTTPException(400, "未配置 LLM 存储路径")
        profile = llm_store.get_profile(profile_id)
        if profile is None:
            raise HTTPException(404, f"LLM profile not found: {profile_id}")
        result = test_llm_connection(profile, llm_store.get_proxy_config(), credential_store)
        return result.model_dump()

    @app.get("/api/llm/proxy")
    def get_llm_proxy():
        if llm_store is None:
            return {"configured": False, "message": "未配置 LLM 存储路径"}
        return {"configured": True, **proxy_to_dict(llm_store.get_proxy_config())}

    @app.put("/api/llm/proxy")
    def save_llm_proxy(req: SaveProxyConfigRequest = Body()):
        if llm_store is None:
            raise HTTPException(400, "未配置 LLM 存储路径")
        from ontology_platform.llm.schema import ProxyConfig

        config = llm_store.save_proxy_config(ProxyConfig.model_validate(req.model_dump()))
        runtime_platform["instance"] = None
        if audit_logger:
            audit_logger.log(
                AuditLogEntry(
                    user_id="admin-ui",
                    action_name="LlmProxyUpdated",
                    target_id="proxy",
                    status="success",
                    success=True,
                    message="更新 LLM 代理配置",
                )
            )
        return proxy_to_dict(config)

    @app.get("/api/llm/active")
    def get_active_llm():
        if llm_store is None:
            return {"configured": False}
        profile = llm_store.get_default_profile()
        if profile is None:
            return {"configured": True, "active": None}
        proxy_cfg = llm_store.get_proxy_config()
        from ontology_platform.llm.proxy import resolve_proxy_used

        return {
            "configured": True,
            "active": llm_store._to_public(llm_store._get_row(profile.id) or {}, credential_store).model_dump(),
            "proxy": proxy_to_dict(proxy_cfg),
            "proxy_will_be_used": resolve_proxy_used(profile, proxy_cfg),
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

    @app.get("/connectors")
    def connectors_page():
        return FileResponse(STATIC_DIR / "connectors.html")

    @app.get("/mappings")
    def mappings_page():
        return FileResponse(STATIC_DIR / "mappings.html")

    @app.get("/settings/llm")
    def llm_settings_page():
        return FileResponse(STATIC_DIR / "llm.html")

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
