from __future__ import annotations

import time
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import StatusCode

from .base import Message, ModelAdapter

_tracer = trace.get_tracer(__name__)


class MetricsAdapter:
    def __init__(self, inner: ModelAdapter) -> None:
        self._inner = inner
        self.last_usage: dict[str, int] = {}

    @property
    def name(self) -> str:
        return self._inner.name

    def complete(
        self,
        messages: list[Message],
        cache_breakpoints: list[int] | None = None,
        model: str = "",
        **kwargs: Any,
    ) -> str:
        span = _tracer.start_span("lena.adapter.complete")
        span.set_attribute("lena.adapter", self._inner.name)
        span.set_attribute("lena.model", model or "")
        span.set_attribute(
            "lena.cache.breakpoints",
            str(cache_breakpoints) if cache_breakpoints else "none",
        )

        t0 = time.perf_counter()
        try:
            result = self._inner.complete(
                messages,
                cache_breakpoints=cache_breakpoints,
                model=model,
                **kwargs,
            )
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(StatusCode.ERROR, str(exc))
            raise
        finally:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            self.last_usage = self._inner.last_usage
            span.set_attribute(
                "lena.cache.hit_tokens",
                self.last_usage.get("cache_read_tokens", 0),
            )
            span.set_attribute(
                "lena.cache.miss_tokens",
                self.last_usage.get("cache_write_tokens", 0),
            )
            span.set_attribute("lena.latency_ms", round(elapsed_ms, 2))
            input_tok = self.last_usage.get("input_tokens", 0)
            cache_read_tok = self.last_usage.get("cache_read_tokens", 0)
            denom = input_tok + cache_read_tok
            hit_rate = cache_read_tok / denom if denom > 0 else 0.0
            span.set_attribute("lena.cache.hit_rate", round(hit_rate, 4))
            span.end()

        return result
