"""Ontology runtime service: query, link traversal, and action execution."""

from __future__ import annotations

import uuid
from typing import Any

from ontology_platform.governance.audit import AuditLogger, AuditLogEntry
from ontology_platform.governance.context import ExecutionContext
from ontology_platform.governance.policy import PolicyEngine
from ontology_platform.ontology.registry import OntologyRegistry
from ontology_platform.ontology.schema import (
    ActionResult,
    LinkInstance,
    OntologyObject,
    PropertyType,
)
from ontology_platform.ontology.store import MemoryStore, SQLiteStore


class OntologyService:
    """Runtime service operating on a registered ontology."""

    def __init__(
        self,
        registry: OntologyRegistry,
        ontology_name: str,
        store: MemoryStore | SQLiteStore | None = None,
        policy: PolicyEngine | None = None,
        audit: AuditLogger | None = None,
    ) -> None:
        self.registry = registry
        self.ontology_name = ontology_name
        self.store = store or MemoryStore()
        self.policy = policy or PolicyEngine()
        self.audit = audit
        self._execution_context = ExecutionContext()
        self._ontology = registry.get(ontology_name)
        if self._ontology is None:
            raise ValueError(f"Ontology not found: {ontology_name}")

    @property
    def ontology(self):
        return self._ontology

    def set_execution_context(self, ctx: ExecutionContext) -> None:
        self._execution_context = ctx

    def get_execution_context(self) -> ExecutionContext:
        return self._execution_context

    def create_object(
        self,
        object_type: str,
        properties: dict[str, Any],
        object_id: str | None = None,
    ) -> OntologyObject:
        type_def = self._ontology.get_object_type(object_type)
        if type_def is None:
            raise ValueError(f"Unknown object type: {object_type}")

        obj_id = object_id or properties.get(type_def.primary_key) or str(uuid.uuid4())
        validated = self._validate_properties(type_def.name, properties, for_create=True)
        validated[type_def.primary_key] = obj_id

        obj = OntologyObject(
            object_type=object_type,
            object_id=obj_id,
            properties=validated,
        )
        return self.store.create_object(obj)

    def get_object(self, object_type: str, object_id: str) -> OntologyObject | None:
        return self.store.get_object(object_type, object_id)

    def search_objects(
        self,
        object_type: str,
        filters: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> list[OntologyObject]:
        type_def = self._ontology.get_object_type(object_type)
        if type_def is None:
            raise ValueError(f"Unknown object type: {object_type}")
        return self.store.list_objects(object_type, filters, limit)

    def create_link(
        self,
        link_type: str,
        source_type: str,
        source_id: str,
        target_type: str,
        target_id: str,
        properties: dict[str, Any] | None = None,
    ) -> LinkInstance:
        link_def = self._ontology.get_link(link_type)
        if link_def is None:
            raise ValueError(f"Unknown link type: {link_type}")
        if link_def.source_type != source_type or link_def.target_type != target_type:
            raise ValueError(
                f"Link type {link_type} expects "
                f"{link_def.source_type}->{link_def.target_type}, "
                f"got {source_type}->{target_type}"
            )
        if self.store.get_object(source_type, source_id) is None:
            raise ValueError(f"Source object not found: {source_type}/{source_id}")
        if self.store.get_object(target_type, target_id) is None:
            raise ValueError(f"Target object not found: {target_type}/{target_id}")

        link = LinkInstance(
            link_type=link_type,
            source_type=source_type,
            source_id=source_id,
            target_type=target_type,
            target_id=target_id,
            properties=properties or {},
        )
        return self.store.create_link(link)

    def traverse_links(
        self,
        object_type: str,
        object_id: str,
        link_type: str | None = None,
        direction: str = "outgoing",
    ) -> list[dict[str, Any]]:
        """Traverse links from an object and return linked objects with metadata."""
        if direction == "outgoing":
            links = self.store.get_links(
                link_type=link_type, source_type=object_type, source_id=object_id
            )
            results = []
            for link in links:
                target = self.store.get_object(link.target_type, link.target_id)
                if target:
                    results.append(
                        {
                            "link_type": link.link_type,
                            "direction": "outgoing",
                            "object": target.model_dump(),
                        }
                    )
            return results

        if direction == "incoming":
            links = self.store.get_links(
                link_type=link_type, target_type=object_type, target_id=object_id
            )
            results = []
            for link in links:
                source = self.store.get_object(link.source_type, link.source_id)
                if source:
                    results.append(
                        {
                            "link_type": link.link_type,
                            "direction": "incoming",
                            "object": source.model_dump(),
                        }
                    )
            return results

        raise ValueError(f"Invalid direction: {direction}")

    def execute_action(
        self,
        action_name: str,
        target_id: str,
        parameters: dict[str, Any] | None = None,
        approved: bool = False,
        context: ExecutionContext | None = None,
    ) -> ActionResult:
        ctx = context or self._execution_context
        action_def = self._ontology.get_action(action_name)
        if action_def is None:
            return self._audit_and_return(
                ctx, action_name, "", target_id, parameters or {}, approved,
                ActionResult(success=False, message=f"Unknown action: {action_name}"),
                status="failed",
            )

        target = self.store.get_object(action_def.target_type, target_id)
        if target is None:
            return self._audit_and_return(
                ctx, action_name, action_def.target_type, target_id, parameters or {}, approved,
                ActionResult(
                    success=False,
                    message=f"Target not found: {action_def.target_type}/{target_id}",
                ),
                status="failed",
            )

        params = parameters or {}

        can_exec, deny_msg = self.policy.can_execute(action_def, ctx)
        if not can_exec:
            return self._audit_and_return(
                ctx, action_name, action_def.target_type, target_id, params, approved,
                ActionResult(success=False, message=deny_msg, denied=True),
                status="denied",
            )

        if action_def.requires_approval and approved:
            can_approve, approve_msg = self.policy.can_approve(action_def, ctx)
            if not can_approve:
                return self._audit_and_return(
                    ctx, action_name, action_def.target_type, target_id, params, approved,
                    ActionResult(success=False, message=approve_msg, denied=True),
                    status="denied",
                )

        if action_def.requires_approval and not approved:
            result = ActionResult(
                success=False,
                message="Action requires approval",
                requires_approval=True,
                data={"action": action_name, "target_id": target_id, "parameters": params},
            )
            return self._audit_and_return(
                ctx, action_name, action_def.target_type, target_id, params, approved,
                result, status="approval_required",
            )

        for param in action_def.parameters:
            if param.required and param.name not in params:
                return self._audit_and_return(
                    ctx, action_name, action_def.target_type, target_id, params, approved,
                    ActionResult(success=False, message=f"Missing required parameter: {param.name}"),
                    status="failed",
                )

        handler = self.registry.get_action_handler(self.ontology_name, action_name)
        if handler is None:
            return self._audit_and_return(
                ctx, action_name, action_def.target_type, target_id, params, approved,
                ActionResult(success=False, message=f"No handler registered for action: {action_name}"),
                status="failed",
            )

        result = handler(self, target, params)
        status = "success" if result.success else "failed"
        return self._audit_and_return(
            ctx, action_name, action_def.target_type, target_id, params, approved,
            result, status=status,
        )

    def _audit_and_return(
        self,
        ctx: ExecutionContext,
        action_name: str,
        target_type: str,
        target_id: str,
        params: dict,
        approved: bool,
        result: ActionResult,
        status: str,
    ) -> ActionResult:
        if self.audit:
            self.audit.log(
                AuditLogEntry(
                    ontology_name=self.ontology_name,
                    user_id=ctx.user_id,
                    roles=ctx.roles,
                    thread_id=ctx.thread_id,
                    action_name=action_name,
                    target_type=target_type,
                    target_id=target_id,
                    parameters=params,
                    status=status,
                    success=result.success,
                    message=result.message,
                    approved=approved,
                )
            )
        return result

    def get_schema_summary(self) -> dict[str, Any]:
        """Return a summary of the ontology schema for agent context."""
        return {
            "name": self._ontology.name,
            "version": self._ontology.version,
            "object_types": [
                {
                    "name": t.name,
                    "display_name": t.display_name,
                    "properties": [p.model_dump() for p in t.properties],
                }
                for t in self._ontology.object_types
            ],
            "links": [l.model_dump() for l in self._ontology.links],
            "actions": [
                {
                    "name": a.name,
                    "display_name": a.display_name,
                    "target_type": a.target_type,
                    "parameters": [p.model_dump() for p in a.parameters],
                    "requires_approval": a.requires_approval,
                    "allowed_roles": a.allowed_roles,
                    "approver_roles": a.approver_roles,
                }
                for a in self._ontology.actions
            ],
        }

    def _validate_properties(
        self,
        object_type: str,
        properties: dict[str, Any],
        for_create: bool = False,
    ) -> dict[str, Any]:
        type_def = self._ontology.get_object_type(object_type)
        if type_def is None:
            raise ValueError(f"Unknown object type: {object_type}")

        validated: dict[str, Any] = {}
        for prop_def in type_def.properties:
            value = properties.get(prop_def.name)
            if value is None:
                if prop_def.required and for_create:
                    raise ValueError(f"Missing required property: {prop_def.name}")
                continue
            validated[prop_def.name] = self._coerce_property(prop_def, value)

        for key, value in properties.items():
            if key not in validated and type_def.get_property(key) is None:
                validated[key] = value

        return validated

    def _coerce_property(self, prop_def, value: Any) -> Any:
        if prop_def.type == PropertyType.STRING:
            return str(value)
        if prop_def.type == PropertyType.INTEGER:
            return int(value)
        if prop_def.type == PropertyType.FLOAT:
            return float(value)
        if prop_def.type == PropertyType.BOOLEAN:
            if isinstance(value, str):
                return value.lower() in ("true", "1", "yes")
            return bool(value)
        if prop_def.type == PropertyType.ENUM:
            if value not in prop_def.enum_values:
                raise ValueError(
                    f"Invalid enum value for {prop_def.name}: {value}. "
                    f"Allowed: {prop_def.enum_values}"
                )
            return value
        return value
