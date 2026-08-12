"""Tests for ontology-browser skill install and local bridge helpers."""

from __future__ import annotations

from pathlib import Path

from ontology_platform.browser_adapter.cli_skill import cmd_install_skill, json_dump
from ontology_platform.browser_adapter.skill_paths import skill_dir


def test_skill_bundle_present():
    src = skill_dir()
    assert (src / "SKILL.md").is_file()
    content = (src / "SKILL.md").read_text(encoding="utf-8")
    assert "name: ontology-browser" in content
    assert "ontology-browser-client" in content


def test_install_skill_to_custom_path(tmp_path: Path):
    dest = tmp_path / "skills" / "ontology-browser"
    code = cmd_install_skill(str(dest), skip_bridge=True)
    assert code == 0
    assert (dest / "SKILL.md").is_file()
    assert (dest / "scripts" / "run-script.py").is_file()


def test_json_dump():
    assert '"ok": true' in json_dump({"ok": True}).replace("True", "true") or "true" in json_dump({"ok": True})
