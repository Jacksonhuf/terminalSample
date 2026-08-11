"""Resolve ontology YAML paths for runtime and CLI use."""

from __future__ import annotations

import os
from pathlib import Path


def resolve_primary_ontology_yaml(
    directory: str | Path,
    explicit_path: str | Path | None = None,
) -> Path | None:
    """Resolve the primary ontology YAML for runtime features.

    Priority:
    1. ``explicit_path`` (CLI flag or constructor argument)
    2. ``ONTOLOGY_YAML`` environment variable
    3. Exactly one ``*.yaml`` file in ``directory``
    4. ``demo_ontology.yaml`` in ``directory`` if it exists
    5. ``None`` — no silent prototype or other app-specific default
    """
    if explicit_path:
        return Path(explicit_path)

    env = os.getenv("ONTOLOGY_YAML")
    if env:
        return Path(env)

    directory = Path(directory)
    yamls = sorted(directory.glob("*.yaml"))
    if len(yamls) == 1:
        return yamls[0]

    demo = directory / "demo_ontology.yaml"
    if demo.exists():
        return demo

    return None
