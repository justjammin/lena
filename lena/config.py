from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "lena.config.yaml"


def _expand_env(text: str) -> str:
    """Replace ${VAR} placeholders with values from the environment."""
    return re.sub(r'\$\{([^}]+)\}', lambda m: os.environ.get(m.group(1), m.group(0)), text)


@dataclass
class AdapterPattern:
    pattern: str
    adapter: str


@dataclass
class RoutingConfig:
    scorer_path: Path
    threshold: int


@dataclass
class Mem0Config:
    vector_store: dict[str, Any]
    embedder: dict[str, Any]


@dataclass
class ZepConfig:
    base_url: str
    api_key: str


@dataclass
class MemoryConfig:
    backend: str
    mem0: Mem0Config
    zep: ZepConfig


@dataclass
class ObservabilityConfig:
    langfuse: dict[str, str]
    otel_endpoint: str


@dataclass
class RegistryConfig:
    manifest_path: Path = field(default_factory=lambda: Path("agents.manifest.yaml"))


@dataclass
class TeamMoatConfig:
    enabled: bool = True
    team_id: str = "default"
    top_k: int = 5


@dataclass
class EmbeddingsConfig:
    provider: str = "ollama"
    model: str = "nomic-embed-text"
    base_url: str = "http://localhost:11434"


@dataclass
class Config:
    models: dict[str, str]
    adapters: list[AdapterPattern]
    routing: RoutingConfig
    memory: MemoryConfig
    observability: ObservabilityConfig
    skills_dir: Path
    registry: RegistryConfig = field(default_factory=RegistryConfig)
    team_moat: TeamMoatConfig = field(default_factory=TeamMoatConfig)
    embeddings: EmbeddingsConfig = field(default_factory=EmbeddingsConfig)


@lru_cache(maxsize=1)
def load_config(config_path: str | None = None) -> Config:
    path = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH
    raw_text = _expand_env(path.read_text())
    raw: dict[str, Any] = yaml.safe_load(raw_text)

    models: dict[str, str] = raw.get("models", {})

    _valid_adapters = {"anthropic", "openai", "gemini", "ollama"}
    adapters = []
    for entry in raw.get("adapters", []):
        a = entry["adapter"]
        if a not in _valid_adapters:
            raise ValueError(f"Unknown adapter '{a}' in lena.config.yaml")
        adapters.append(AdapterPattern(pattern=entry["pattern"], adapter=a))

    routing_raw = raw.get("routing", {})
    scorer_raw = routing_raw.get("scorer_path", "skills/lena/routing_score.py")
    # Resolve relative to the config file's directory so callers aren't CWD-sensitive.
    scorer_path = (path.parent / scorer_raw).resolve()

    routing = RoutingConfig(
        scorer_path=scorer_path,
        threshold=int(routing_raw.get("threshold", 70)),
    )

    mem_raw = raw.get("memory", {})
    mem0_raw = mem_raw.get("mem0", {})
    zep_raw = mem_raw.get("zep", {})
    memory = MemoryConfig(
        backend=mem_raw.get("backend", "mem0"),
        mem0=Mem0Config(
            vector_store=mem0_raw.get("vector_store", {}),
            embedder=mem0_raw.get("embedder", {}),
        ),
        zep=ZepConfig(
            base_url=zep_raw.get("base_url", "http://localhost:8000"),
            api_key=os.environ.get("ZEP_API_KEY", zep_raw.get("api_key", "")),
        ),
    )

    obs_raw = raw.get("observability", {})
    lf_raw = obs_raw.get("langfuse", {})
    langfuse = {
        "host": lf_raw.get("host", "http://localhost:3000"),
        "public_key": os.environ.get("LANGFUSE_PUBLIC_KEY", lf_raw.get("public_key", "")),
        "secret_key": os.environ.get("LANGFUSE_SECRET_KEY", lf_raw.get("secret_key", "")),
    }
    observability = ObservabilityConfig(
        langfuse=langfuse,
        otel_endpoint=obs_raw.get("otel_endpoint", ""),
    )

    # skills_dir lives at project-root/skills, one level above the config file's parent (lena/)
    skills_dir = (path.parent / "skills").resolve()

    # --- registry ---
    reg_raw = raw.get("registry", {})
    manifest_raw = reg_raw.get("manifest_path", "agents.manifest.yaml")
    manifest_path = (path.parent / manifest_raw).resolve()
    registry = RegistryConfig(manifest_path=manifest_path)

    # --- team_moat ---
    tm_raw = raw.get("team_moat", {})
    team_moat = TeamMoatConfig(
        enabled=bool(tm_raw.get("enabled", True)),
        team_id=str(tm_raw.get("team_id", "default")),
        top_k=int(tm_raw.get("top_k", 5)),
    )

    # --- embeddings ---
    emb_raw = raw.get("embeddings", {})
    embeddings = EmbeddingsConfig(
        provider=str(emb_raw.get("provider", "ollama")),
        model=str(emb_raw.get("model", "nomic-embed-text")),
        base_url=str(emb_raw.get("base_url", "http://localhost:11434")),
    )

    return Config(
        models=models,
        adapters=adapters,
        routing=routing,
        memory=memory,
        observability=observability,
        skills_dir=skills_dir,
        registry=registry,
        team_moat=team_moat,
        embeddings=embeddings,
    )
