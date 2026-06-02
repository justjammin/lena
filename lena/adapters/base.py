from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

from typing_extensions import TypedDict

Role = Literal["system", "user", "assistant", "tool"]


class Message(TypedDict, total=False):
    role: Role
    content: str | list[dict]
    name: str
    tool_call_id: str
    tool_calls: list[dict]  # OpenAI-wire shape stored in assistant messages


class ToolCall(TypedDict):
    id: str
    name: str
    arguments: dict  # already-parsed dict; adapters normalize before returning


@dataclass(frozen=True)
class Completion:
    """Return value from ModelAdapter.complete.

    Deliberately a dataclass (not TypedDict) so callers access .content and
    .tool_calls as attributes. TypedDict would require ["content"] syntax,
    which breaks backward-compat callers that do ``output = adapter.complete(...)``.
    """

    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)


@runtime_checkable
class ModelAdapter(Protocol):
    name: str
    last_usage: dict[str, int]

    def complete(
        self,
        messages: list[Message],
        cache_breakpoints: list[int] | None = None,
        model: str = "",
        tools: list[dict] | None = None,
        **kwargs: Any,
    ) -> Completion: ...
