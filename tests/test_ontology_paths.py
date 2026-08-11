"""Tests for ontology YAML path resolution."""

from pathlib import Path

from ontology_platform.ontology.paths import resolve_primary_ontology_yaml

EXAMPLES = Path(__file__).parent.parent / "examples"


class TestResolvePrimaryOntologyYaml:
    def test_explicit_path(self, tmp_path: Path):
        yaml_file = tmp_path / "custom.yaml"
        yaml_file.write_text("name: custom\n", encoding="utf-8")
        assert resolve_primary_ontology_yaml(tmp_path, yaml_file) == yaml_file

    def test_demo_fallback(self, tmp_path: Path):
        demo = tmp_path / "demo_ontology.yaml"
        demo.write_text("name: demo\n", encoding="utf-8")
        (tmp_path / "other.yaml").write_text("name: other\n", encoding="utf-8")
        assert resolve_primary_ontology_yaml(tmp_path) == demo

    def test_single_yaml_in_directory(self, tmp_path: Path):
        only = tmp_path / "only.yaml"
        only.write_text("name: only\n", encoding="utf-8")
        assert resolve_primary_ontology_yaml(tmp_path) == only

    def test_no_default_when_ambiguous(self, tmp_path: Path):
        (tmp_path / "a.yaml").write_text("name: a\n", encoding="utf-8")
        (tmp_path / "b.yaml").write_text("name: b\n", encoding="utf-8")
        assert resolve_primary_ontology_yaml(tmp_path) is None

    def test_examples_dir_resolves_demo(self):
        resolved = resolve_primary_ontology_yaml(EXAMPLES)
        assert resolved is not None
        assert resolved.name == "demo_ontology.yaml"
