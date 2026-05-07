"""Tests for AgentRegistry — manifest loading, lookup, duplicate detection."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_manifest(tmp_path: Path, data: dict) -> Path:
    manifest = tmp_path / "agents.manifest.yaml"
    manifest.write_text(yaml.dump(data))
    return manifest


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAgentRegistry:
    def test_load_valid_manifest(self, tmp_path):
        from lena.registry import AgentRegistry

        manifest = _write_manifest(
            tmp_path,
            {
                "version": 1,
                "agents": {
                    "backend": [
                        {
                            "name": "backend-developer",
                            "path": ".claude/agents/backend-developer.md",
                            "tools": ["Read", "Edit"],
                            "model": "gpt-5.5",
                        }
                    ],
                    "testing": [
                        {
                            "name": "test-automator",
                            "path": ".claude/agents/test-automator.md",
                            "tools": ["Read", "Bash"],
                            "model": "gpt-5.5",
                        }
                    ],
                },
            },
        )

        registry = AgentRegistry(manifest)
        registry.load()

        assert len(registry.all()) == 2

    def test_get_by_name_returns_correct_spec(self, tmp_path):
        from lena.registry import AgentRegistry, AgentSpec

        manifest = _write_manifest(
            tmp_path,
            {
                "version": 1,
                "agents": {
                    "backend": [
                        {
                            "name": "backend-developer",
                            "path": ".claude/agents/backend-developer.md",
                            "tools": ["Read", "Edit"],
                            "model": "gpt-5.5",
                        }
                    ],
                },
            },
        )

        registry = AgentRegistry(manifest)
        registry.load()

        spec = registry.get("backend-developer")
        assert spec is not None
        assert isinstance(spec, AgentSpec)
        assert spec.name == "backend-developer"
        assert spec.domain == "backend"
        assert spec.tools == ["Read", "Edit"]
        assert spec.model == "gpt-5.5"

    def test_get_unknown_name_returns_none(self, tmp_path):
        from lena.registry import AgentRegistry

        manifest = _write_manifest(tmp_path, {"version": 1, "agents": {}})
        registry = AgentRegistry(manifest)
        registry.load()

        assert registry.get("nonexistent") is None

    def test_by_domain_returns_specs(self, tmp_path):
        from lena.registry import AgentRegistry

        manifest = _write_manifest(
            tmp_path,
            {
                "version": 1,
                "agents": {
                    "backend": [
                        {"name": "backend-developer", "path": "", "tools": [], "model": "gpt-5.5"},
                    ],
                    "database": [
                        {"name": "database-optimizer", "path": "", "tools": [], "model": "gpt-5.5"},
                    ],
                },
            },
        )

        registry = AgentRegistry(manifest)
        registry.load()

        backend_specs = registry.by_domain("backend")
        assert len(backend_specs) == 1
        assert backend_specs[0].name == "backend-developer"

        db_specs = registry.by_domain("database")
        assert len(db_specs) == 1
        assert db_specs[0].name == "database-optimizer"

    def test_by_domain_unknown_returns_empty(self, tmp_path):
        from lena.registry import AgentRegistry

        manifest = _write_manifest(tmp_path, {"version": 1, "agents": {}})
        registry = AgentRegistry(manifest)
        registry.load()

        assert registry.by_domain("nonexistent") == []

    def test_duplicate_name_across_domains_raises(self, tmp_path):
        from lena.registry import AgentRegistry, DuplicateAgentError

        manifest = _write_manifest(
            tmp_path,
            {
                "version": 1,
                "agents": {
                    "backend": [
                        {"name": "shared-agent", "path": "", "tools": [], "model": "gpt-5.5"},
                    ],
                    "testing": [
                        {"name": "shared-agent", "path": "", "tools": [], "model": "gpt-5.5"},
                    ],
                },
            },
        )

        registry = AgentRegistry(manifest)
        with pytest.raises(DuplicateAgentError, match="shared-agent"):
            registry.load()

    def test_all_returns_all_specs(self, tmp_path):
        from lena.registry import AgentRegistry

        manifest = _write_manifest(
            tmp_path,
            {
                "version": 1,
                "agents": {
                    "backend": [
                        {"name": "backend-developer", "path": "", "tools": [], "model": "gpt-5.5"},
                    ],
                    "frontend": [
                        {"name": "frontend-developer", "path": "", "tools": [], "model": "gpt-5.5"},
                    ],
                    "devops": [
                        {"name": "devops-engineer", "path": "", "tools": [], "model": "gpt-5.5"},
                    ],
                },
            },
        )

        registry = AgentRegistry(manifest)
        registry.load()

        all_specs = registry.all()
        names = {s.name for s in all_specs}
        assert names == {"backend-developer", "frontend-developer", "devops-engineer"}

    def test_domain_is_set_on_spec(self, tmp_path):
        from lena.registry import AgentRegistry

        manifest = _write_manifest(
            tmp_path,
            {
                "version": 1,
                "agents": {
                    "architecture": [
                        {"name": "architect-reviewer", "path": "", "tools": [], "model": "gpt-5.5"},
                    ],
                },
            },
        )

        registry = AgentRegistry(manifest)
        registry.load()

        spec = registry.get("architect-reviewer")
        assert spec is not None
        assert spec.domain == "architecture"

    def test_load_real_manifest(self):
        """Smoke test against the actual agents.manifest.yaml in the project root."""
        project_root = Path(__file__).parent.parent
        manifest_path = project_root / "agents.manifest.yaml"
        if not manifest_path.exists():
            pytest.skip("agents.manifest.yaml not found")

        from lena.registry import AgentRegistry

        registry = AgentRegistry(manifest_path)
        registry.load()

        assert len(registry.all()) > 0
        assert registry.get("backend-developer") is not None
        assert len(registry.by_domain("backend")) > 0
