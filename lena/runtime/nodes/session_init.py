from __future__ import annotations

import logging
from pathlib import Path

from ...config import load_config
from ...memory.mem0_adapter import Mem0Adapter
from ...memory.zep_adapter import ZepAdapter
from ..state import AgentState

_log = logging.getLogger(__name__)

# Module-level singletons (lazy-init so imports stay fast)
_mem0: Mem0Adapter | None = None
_zep: ZepAdapter | None = None


def _get_mem0() -> Mem0Adapter:
    global _mem0
    if _mem0 is None:
        _mem0 = Mem0Adapter()
    return _mem0


def _get_zep() -> ZepAdapter:
    global _zep
    if _zep is None:
        cfg = load_config()
        _zep = ZepAdapter(
            base_url=cfg.memory.zep.base_url,
            api_key=cfg.memory.zep.api_key,
        )
    return _zep


def session_init(state: AgentState) -> dict:
    config = load_config()
    mem0_session = state["mem0_session_id"]
    zep_session = state["zep_session_id"]
    task = state["task"]

    # --- Load SKILL.md ---
    skill_path = config.skills_dir / "lena" / "SKILL.md"
    skill_content = ""
    try:
        skill_content = skill_path.read_text()
    except FileNotFoundError:
        _log.warning("SKILL.md not found at %s", skill_path)

    # --- Recall project context from mem0 ---
    mem0 = _get_mem0()
    project_context = mem0.recall("project_context", mem0_session) or ""

    # --- Search Zep for task-relevant facts ---
    zep = _get_zep()
    facts = zep.search_facts(zep_session, task, k=5)
    facts_text = "\n".join(f"- {f}" for f in facts) if facts else ""

    # --- Build system message ---
    system_parts = [skill_content]
    if project_context:
        system_parts.append(f"\n## Project Context\n{project_context}")
    if facts_text:
        system_parts.append(f"\n## Relevant Facts\n{facts_text}")

    system_message = {
        "role": "system",
        "content": "\n".join(system_parts),
    }
    user_message = {
        "role": "user",
        "content": task,
    }

    result: dict = {
        "messages": [system_message, user_message],
        "current_node": "session_init",
    }
    # Preserve CLI --model override — only set default if no model was pre-set.
    if not state.get("model"):
        result["model"] = config.models.get("default", "claude-sonnet-4-6")
    return result
