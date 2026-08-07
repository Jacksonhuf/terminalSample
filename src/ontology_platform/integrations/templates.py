"""Jinja2 template rendering for outbound messages."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

DEFAULT_TEMPLATE_DIR = Path(__file__).parent / "templates"


class TemplateRenderer:
    def __init__(self, template_dir: str | Path | None = None) -> None:
        path = Path(template_dir) if template_dir else DEFAULT_TEMPLATE_DIR
        self._env = Environment(
            loader=FileSystemLoader(str(path)),
            autoescape=select_autoescape(enabled_extensions=()),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, template_id: str, context: dict, *, channel: str = "chat") -> tuple[str, str]:
        """Return (subject, body) for a template id."""
        subject_name = f"{channel}/{template_id}.subject.txt"
        body_name = f"{channel}/{template_id}.body.txt"
        subject = ""
        try:
            subject = self._env.get_template(subject_name).render(**context).strip()
        except Exception:
            subject = context.get("subject", "")
        body = self._env.get_template(body_name).render(**context).strip()
        return subject, body
