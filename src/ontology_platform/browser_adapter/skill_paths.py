"""Resolve bundled ontology-browser skill directory."""

from __future__ import annotations

from pathlib import Path


def skill_dir() -> Path:
    bundled = Path(__file__).resolve().parent / "skill"
    if (bundled / "SKILL.md").is_file():
        return bundled
    repo = Path(__file__).resolve().parents[3] / "skills" / "ontology-browser"
    if (repo / "SKILL.md").is_file():
        return repo
    raise FileNotFoundError("ontology-browser skill bundle not found")
