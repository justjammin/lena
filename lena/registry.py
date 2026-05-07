from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_log = logging.getLogger(__name__)


class DuplicateAgentError(Exception):
    """Raised when the same agent name appears in two or more domains."""


@dataclass
class AgentSpec:
    name: str
    path: str
    tools: list[str]
    model: str
    domain: str


class AgentRegistry:
    def __init__(self, manifest_path: Path) -> None:
        self._manifest_path = manifest_path
        self._by_name: dict[str, AgentSpec] = {}
        self._by_domain: dict[str, list[AgentSpec]] = {}

    def load(self) -> None:
        raw: dict = yaml.safe_load(self._manifest_path.read_text())
        agents_raw: dict = raw.get("agents", {})

        by_name: dict[str, AgentSpec] = {}
        by_domain: dict[str, list[AgentSpec]] = {}

        for domain_key, entries in agents_raw.items():
            if not isinstance(entries, list):
                _log.warning("Skipping non-list entry for domain '%s'", domain_key)
                continue
            domain_specs: list[AgentSpec] = []
            for entry in entries:
                name = entry["name"]
                if name in by_name:
                    raise DuplicateAgentError(
                        f"Agent '{name}' appears in multiple domains: "
                        f"'{by_name[name].domain}' and '{domain_key}'"
                    )
                spec = AgentSpec(
                    name=name,
                    path=entry.get("path", ""),
                    tools=list(entry.get("tools", [])),
                    model=entry.get("model", ""),
                    domain=domain_key,
                )
                by_name[name] = spec
                domain_specs.append(spec)
            by_domain[domain_key] = domain_specs

        self._by_name = by_name
        self._by_domain = by_domain

    def get(self, name: str) -> AgentSpec | None:
        return self._by_name.get(name)

    def by_domain(self, domain: str) -> list[AgentSpec]:
        return list(self._by_domain.get(domain, []))

    def all(self) -> list[AgentSpec]:
        return list(self._by_name.values())
