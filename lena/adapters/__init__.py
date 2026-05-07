from __future__ import annotations

import fnmatch
from typing import TYPE_CHECKING

from .base import ModelAdapter
from .metrics import MetricsAdapter
from ..config import load_config

if TYPE_CHECKING:
    pass


class UnknownModelError(ValueError):
    pass


def get_adapter(model: str) -> MetricsAdapter:
    """Return a MetricsAdapter wrapping the correct concrete adapter for *model*.

    Pattern matching uses fnmatch against the adapter patterns defined in lena.config.yaml.
    Raises UnknownModelError if no pattern matches.
    """
    config = load_config()
    for entry in config.adapters:
        if fnmatch.fnmatchcase(model, entry.pattern):
            adapter_name = entry.adapter
            break
    else:
        raise UnknownModelError(
            f"No adapter pattern matched model {model!r}. "
            "Add an entry to lena.config.yaml adapters list."
        )

    return MetricsAdapter(_build_adapter(adapter_name))


def _build_adapter(name: str):
    if name == "anthropic":
        from .anthropic import AnthropicAdapter
        return AnthropicAdapter()
    if name == "openai":
        from .openai import OpenAIAdapter
        return OpenAIAdapter()
    if name == "gemini":
        from .gemini import GeminiAdapter
        return GeminiAdapter()
    if name == "ollama":
        from .ollama import OllamaAdapter
        return OllamaAdapter()
    raise UnknownModelError(f"Unknown adapter type: {name!r}")
