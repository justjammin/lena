from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from ...adapters import get_adapter
from ...adapters.base import Completion, ToolCall
from ...config import load_config
from ..handoff import HandoffTransformer
from ..state import AgentState
from ..tools import build_tool_schema, execute_tool

if TYPE_CHECKING:
    from ...registry import AgentRegistry, AgentSpec

_log = logging.getLogger(__name__)

_transformer = HandoffTransformer(cap=500)

MAX_TOOL_ITERS = 8

# ---------------------------------------------------------------------------
# Registry singleton
# ---------------------------------------------------------------------------

_registry_instance: "AgentRegistry | None" = None


def _get_registry() -> "AgentRegistry | None":
    """Return a lazily loaded AgentRegistry, or None if manifest is missing/unreadable."""
    global _registry_instance
    if _registry_instance is not None:
        return _registry_instance
    try:
        from ...registry import AgentRegistry

        config = load_config()
        manifest_path = config.registry.manifest_path
        if not manifest_path.exists():
            _log.debug("executor: manifest not found at %s — registry disabled", manifest_path)
            return None
        reg = AgentRegistry(manifest_path=manifest_path)
        reg.load()
        _registry_instance = reg
        return reg
    except Exception as exc:
        _log.debug("executor: failed to load registry: %s — registry disabled", exc)
        return None


# ---------------------------------------------------------------------------
# Persona injection
# ---------------------------------------------------------------------------


def _inject_persona(messages: list[dict], spec: "AgentSpec", hat: str) -> None:
    """Append persona .md text and hat name to the first system message (in-place).

    If no system message exists, prepends one. Errors reading the persona file
    are logged and silently skipped so the loop still proceeds.
    """
    persona_text = ""
    if spec.path:
        try:
            config = load_config()
            manifest_dir = config.registry.manifest_path.parent
            persona_path = (manifest_dir / spec.path).resolve()
            persona_text = persona_path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            _log.debug("executor: could not read persona file for %s: %s", hat, exc)

    injection = f"\n\n## Persona: {hat}"
    if persona_text:
        injection += f"\n{persona_text}"

    # Find and replace the first system message (copy, not mutate — branches share the
    # underlying dicts via shallow AgentState copy, so in-place mutation causes
    # cross-branch persona contamination in parallel execution).
    for i, msg in enumerate(messages):
        if msg.get("role") == "system":
            content = msg.get("content", "")
            if isinstance(content, str):
                messages[i] = {**msg, "content": content + injection}
            return  # replaced in list

    # No system message found — prepend one.
    messages.insert(0, {"role": "system", "content": injection.lstrip()})


# ---------------------------------------------------------------------------
# Wire-shape conversion helpers
# ---------------------------------------------------------------------------


def _to_wire_toolcall(tc: ToolCall) -> dict:
    """Convert a Completion ToolCall (parsed args) to OpenAI wire format for storage."""
    return {
        "id": tc["id"],
        "type": "function",
        "function": {
            "name": tc["name"],
            "arguments": json.dumps(tc["arguments"]),
        },
    }


# ---------------------------------------------------------------------------
# Shared bounded tool loop
# ---------------------------------------------------------------------------


def run_tool_loop(
    adapter,
    messages: list[dict],
    model: str,
    cache_breakpoints: list[int] | None,
    tool_schema: list[dict] | None,
) -> tuple[str, list[dict]]:
    """Execute the act/observe loop up to MAX_TOOL_ITERS iterations.

    Returns (final_content, new_messages) where new_messages contains only
    the delta produced this invocation (assistant + tool turns).
    """
    new_messages: list[dict] = []
    final_content = ""

    for _ in range(MAX_TOOL_ITERS):
        try:
            completion: Completion = adapter.complete(
                messages,
                cache_breakpoints=cache_breakpoints,
                model=model,
                tools=tool_schema,
            )
        except Exception as exc:
            _log.error("adapter.complete failed: %s", exc)
            final_content = f"[executor error: {exc}]"
            err_msg: dict = {"role": "assistant", "content": final_content}
            new_messages.append(err_msg)
            break

        final_content = completion.content
        assistant_msg: dict = {"role": "assistant", "content": completion.content}
        if completion.tool_calls:
            assistant_msg["tool_calls"] = [_to_wire_toolcall(tc) for tc in completion.tool_calls]
        messages.append(assistant_msg)
        new_messages.append(assistant_msg)

        if not completion.tool_calls:
            break  # Final text answer — done.

        for tc in completion.tool_calls:
            result = execute_tool(tc["name"], tc["arguments"])
            tool_msg: dict = {
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result,
            }
            messages.append(tool_msg)
            new_messages.append(tool_msg)

    return final_content, new_messages


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------


def executor(state: AgentState) -> dict:
    model = state["model"]
    adapter = get_adapter(model)

    messages: list[dict] = list(state["messages"])

    # --- Registry + persona + tool wiring ---
    hat = state.get("hat") or ""
    spec = None
    tool_schema: list[dict] | None = None

    registry = _get_registry()
    if registry is not None and hat:
        spec = registry.get(hat)
        if spec is not None:
            tool_schema = build_tool_schema(spec.tools) or None
            _inject_persona(messages, spec, hat)
            _log.debug("executor: loaded spec for hat=%s tools=%s", hat, spec.tools)
        else:
            _log.debug("executor: no spec found for hat=%s — running without tools/persona", hat)

    # --- HandoffTransformer context injection: once, before loop ---
    prior = state.get("upstream_context")
    if prior or len(messages) > 2:
        compressed = _transformer.compress(messages, prior)
        context_msg: dict = {"role": "user", "content": compressed}
        insert_at = len(messages)
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "user":
                insert_at = i
                break
        messages = messages[:insert_at] + [context_msg] + messages[insert_at:]

    final_content, new_messages = run_tool_loop(
        adapter,
        messages,
        model,
        cache_breakpoints=state.get("cache_breakpoints") or None,
        tool_schema=tool_schema,
    )

    return {
        "messages": new_messages,
        "upstream_context": final_content,
        "current_node": "executor",
    }
