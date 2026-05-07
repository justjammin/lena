from __future__ import annotations

from typing import Any, Literal, Protocol, runtime_checkable

from typing_extensions import TypedDict

Role = Literal["system", "user", "assistant", "tool"]


class Message(TypedDict, total=False):
    role: Role
    content: str | list[dict]
    name: str
    tool_call_id: str


@runtime_checkable
class ModelAdapter(Protocol):
    name: str
    last_usage: dict[str, int]

    def complete(
        self,
        messages: list[Message],
        cache_breakpoints: list[int] | None = None,
        model: str = "",
        **kwargs: Any,
    ) -> str: ...
