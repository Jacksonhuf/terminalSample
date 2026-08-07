"""Governance policy for outbound notifications."""

from __future__ import annotations

from ontology_platform.governance.context import ExecutionContext
from ontology_platform.integrations.schema import ChannelType
from ontology_platform.ontology.service import OntologyService


class OutboundPolicy:
    """Validate who can send messages and to whom."""

    def __init__(
        self,
        *,
        allowed_roles: list[str] | None = None,
        max_recipients: int = 10,
        require_person_in_ontology: bool = True,
    ) -> None:
        self.allowed_roles = allowed_roles or ["operator", "admin"]
        self.max_recipients = max_recipients
        self.require_person_in_ontology = require_person_in_ontology

    def can_send(self, ctx: ExecutionContext, channel: ChannelType) -> tuple[bool, str]:
        if "admin" in ctx.roles:
            return True, ""
        if not any(r in self.allowed_roles for r in ctx.roles):
            return False, f"角色 {ctx.roles} 无权发送 {channel.value} 消息"
        if channel == ChannelType.EMAIL and "viewer" in ctx.roles and "operator" not in ctx.roles:
            return False, "viewer 不能发送邮件"
        return True, ""

    def resolve_recipients(
        self,
        service: OntologyService,
        person_ids: list[str],
        *,
        channel: ChannelType,
    ) -> tuple[list[str], str]:
        if len(person_ids) > self.max_recipients:
            return [], f"收件人超过上限 {self.max_recipients}"

        addresses: list[str] = []
        for person_id in person_ids:
            person = service.get_object("Person", person_id)
            if person is None:
                if self.require_person_in_ontology:
                    return [], f"人员不存在: {person_id}"
                if channel == ChannelType.CHAT:
                    addresses.append(person_id)
                else:
                    addresses.append(person_id)
                continue

            if channel == ChannelType.CHAT:
                im_user = person.properties.get("im_user_id") or person_id
                addresses.append(str(im_user))
            else:
                email = person.properties.get("email")
                if not email:
                    return [], f"人员 {person_id} 未配置 email"
                addresses.append(str(email))

        return addresses, ""
