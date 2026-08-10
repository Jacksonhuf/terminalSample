"""Orchestrate LLM Computer Use capture runs."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from ontology_platform.connector.capture.llm_agent import LlmCaptureAgent
from ontology_platform.connector.schema import CaptureBatch, CaptureRecord


class CaptureRunError(RuntimeError):
    """Raised when capture execution fails."""


class CaptureRunner:
    """Execute a Computer Use capture task via LLM agent or mock data."""

    def __init__(
        self,
        chat_model: BaseChatModel | None = None,
        *,
        mock: bool = False,
        max_steps: int = 25,
    ) -> None:
        self.chat_model = chat_model
        self.mock = mock or os.environ.get("ONTOLOGY_CAPTURE_MOCK", "").lower() in ("1", "true", "yes")
        self.max_steps = max_steps

    def execute(self, task: dict[str, Any], credentials: dict[str, str] | None = None) -> CaptureBatch:
        credentials = credentials or {}
        if self.mock:
            return self._mock_capture(task)
        if self.chat_model is None:
            raise CaptureRunError("未配置 LLM，无法执行 Computer Use 采集（可设置 ONTOLOGY_CAPTURE_MOCK=1 使用演示数据）")
        agent = LlmCaptureAgent(self.chat_model, max_steps=self.max_steps)
        try:
            return agent.run(task, credentials)
        except Exception as exc:
            raise CaptureRunError(str(exc)) from exc

    def _mock_capture(self, task: dict[str, Any]) -> CaptureBatch:
        connector = str(task.get("connector", ""))
        sample = _find_sample_capture(connector)
        data = json.loads(sample.read_text(encoding="utf-8"))
        records = [
            CaptureRecord(
                record_type=r["record_type"],
                external_id=r["external_id"],
                payload=dict(r.get("payload") or {}),
            )
            for r in data.get("records", [])
        ]
        if not records:
            raise CaptureRunError(f"样例采集文件无记录: {sample}")
        return CaptureBatch(
            connector=connector,
            run_id=task.get("run_id"),
            source_url=str(task.get("source_url") or data.get("source_url", "")),
            records=records,
            metadata={"mock": True, "sample_file": str(sample)},
        )


def _find_sample_capture(connector_name: str) -> Path:
    root = Path(__file__).resolve().parents[4]
    candidates = [
        root / "examples" / "captures" / f"{connector_name}_sample.json",
        root / "examples" / "captures" / "prototype_erp_sample.json",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise CaptureRunError(f"未找到样例采集文件: {connector_name}_sample.json")
