"""RBAC policy engine for ontology actions."""

from __future__ import annotations

from ontology_platform.governance.context import ExecutionContext
from ontology_platform.ontology.schema import ActionDef


# Built-in role capabilities (Mode A — self-hosted governance)
ROLE_HIERARCHY = {
    "admin": {"execute", "approve", "query"},
    "operator": {"execute", "query"},
    "viewer": {"query"},
}


class PolicyEngine:
    """Check whether a user may execute or approve an ontology action."""

    def can_execute(self, action: ActionDef, ctx: ExecutionContext) -> tuple[bool, str]:
        if ctx.is_viewer():
            return False, "viewer 角色仅可查询，不可执行写操作"

        if ctx.is_admin():
            return True, ""

        allowed = set(action.allowed_roles or [])
        if not allowed:
            # Default: operator and admin may execute
            if ctx.has_role("operator") or ctx.has_role("admin"):
                return True, ""
            return False, f"角色 {ctx.roles} 无权执行动作 {action.name}"

        if allowed.intersection(ctx.roles):
            return True, ""
        return False, f"动作 {action.name} 需要角色 {sorted(allowed)}，当前: {ctx.roles}"

    def can_approve(self, action: ActionDef, ctx: ExecutionContext) -> tuple[bool, str]:
        if ctx.is_admin():
            return True, ""

        approvers = set(action.approver_roles or ["admin"])
        if approvers.intersection(ctx.roles):
            return True, ""
        return False, f"动作 {action.name} 需要审批角色 {sorted(approvers)}，当前: {ctx.roles}"

    def can_query(self, ctx: ExecutionContext) -> bool:
        if ctx.is_admin() or ctx.has_role("operator") or ctx.has_role("viewer"):
            return True
        return bool(ROLE_HIERARCHY.get(ctx.roles[0] if ctx.roles else "", set()) & {"query"})
