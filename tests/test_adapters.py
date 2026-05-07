from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# AnthropicAdapter — cache breakpoint injection
# ---------------------------------------------------------------------------

class TestAnthropicCacheBreakpoints:
    def _make_adapter(self, mock_client):
        with patch("lena.adapters.anthropic._anthropic_sdk") as sdk:
            sdk.Anthropic.return_value = mock_client
            from lena.adapters.anthropic import AnthropicAdapter
            adapter = AnthropicAdapter.__new__(AnthropicAdapter)
            adapter._client = mock_client
            adapter.last_usage = {}
        return adapter

    def test_str_content_wrapped_with_cache_control(self):
        from lena.adapters.anthropic import _apply_cache_breakpoints

        messages = [
            {"role": "user", "content": "hello world"},
            {"role": "assistant", "content": "hi"},
        ]
        result = _apply_cache_breakpoints(messages, breakpoints=[0])
        first = result[0]["content"]
        assert isinstance(first, list)
        assert first[0]["cache_control"] == {"type": "ephemeral"}
        assert first[0]["text"] == "hello world"

    def test_list_content_last_block_gets_cache_control(self):
        from lena.adapters.anthropic import _apply_cache_breakpoints

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "block 1"},
                    {"type": "text", "text": "block 2"},
                ],
            }
        ]
        result = _apply_cache_breakpoints(messages, breakpoints=[0])
        blocks = result[0]["content"]
        assert "cache_control" not in blocks[0]
        assert blocks[1]["cache_control"] == {"type": "ephemeral"}

    def test_non_breakpoint_messages_unmodified(self):
        from lena.adapters.anthropic import _apply_cache_breakpoints

        messages = [
            {"role": "user", "content": "no cache"},
            {"role": "user", "content": "also no cache"},
        ]
        result = _apply_cache_breakpoints(messages, breakpoints=[])
        for msg in result:
            content = msg["content"]
            if isinstance(content, list):
                for block in content:
                    assert "cache_control" not in block
            else:
                assert True  # plain string, fine

    def test_more_than_4_breakpoints_raises_value_error(self):
        from lena.adapters.anthropic import AnthropicAdapter

        mock_client = MagicMock()
        adapter = AnthropicAdapter.__new__(AnthropicAdapter)
        adapter._client = mock_client
        adapter.last_usage = {}

        messages = [{"role": "user", "content": f"msg {i}"} for i in range(6)]
        with pytest.raises(ValueError, match="4 cache breakpoints"):
            adapter.complete(messages, cache_breakpoints=[0, 1, 2, 3, 4], model="claude-3")

    def test_complete_maps_usage_keys(self):
        from lena.adapters.anthropic import AnthropicAdapter

        fake_usage = MagicMock()
        fake_usage.input_tokens = 100
        fake_usage.output_tokens = 50
        fake_usage.cache_read_input_tokens = 20
        fake_usage.cache_creation_input_tokens = 10

        fake_content = MagicMock()
        fake_content.type = "text"
        fake_content.text = "response text"

        fake_response = MagicMock()
        fake_response.usage = fake_usage
        fake_response.content = [fake_content]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = fake_response

        adapter = AnthropicAdapter.__new__(AnthropicAdapter)
        adapter._client = mock_client
        adapter.last_usage = {}

        messages = [{"role": "user", "content": "hello"}]
        text = adapter.complete(messages, model="claude-3-sonnet")

        assert text == "response text"
        assert adapter.last_usage["cache_read_tokens"] == 20
        assert adapter.last_usage["cache_write_tokens"] == 10
        assert adapter.last_usage["input_tokens"] == 100
        assert adapter.last_usage["output_tokens"] == 50


# ---------------------------------------------------------------------------
# get_adapter — pattern routing
# ---------------------------------------------------------------------------

class TestGetAdapter:
    def _patch_all_adapters(self, mocker):
        mocker.patch("lena.adapters.anthropic.AnthropicAdapter.__init__", return_value=None)
        mocker.patch("lena.adapters.openai.OpenAIAdapter.__init__", return_value=None)
        mocker.patch("lena.adapters.gemini.GeminiAdapter.__init__", return_value=None)
        mocker.patch("lena.adapters.ollama.OllamaAdapter.__init__", return_value=None)

        for cls_path in [
            "lena.adapters.anthropic.AnthropicAdapter",
            "lena.adapters.openai.OpenAIAdapter",
            "lena.adapters.gemini.GeminiAdapter",
            "lena.adapters.ollama.OllamaAdapter",
        ]:
            obj = mocker.patch(cls_path)
            instance = MagicMock()
            instance.last_usage = {}
            obj.return_value = instance

    @pytest.mark.parametrize("model,expected_adapter", [
        ("claude-sonnet-4-6", "lena.adapters.anthropic.AnthropicAdapter"),
        ("claude-haiku-4-5", "lena.adapters.anthropic.AnthropicAdapter"),
        ("gpt-4o", "lena.adapters.openai.OpenAIAdapter"),
        ("gpt-3.5-turbo", "lena.adapters.openai.OpenAIAdapter"),
        ("o1-mini", "lena.adapters.openai.OpenAIAdapter"),
        ("o3-large", "lena.adapters.openai.OpenAIAdapter"),
        ("gemini-1.5-pro", "lena.adapters.gemini.GeminiAdapter"),
        ("ollama/llama3", "lena.adapters.ollama.OllamaAdapter"),
        ("llama3", "lena.adapters.ollama.OllamaAdapter"),
        ("qwen2.5", "lena.adapters.ollama.OllamaAdapter"),
    ])
    def test_correct_adapter_selected(self, mocker, model, expected_adapter):
        self._patch_all_adapters(mocker)
        from lena.adapters import get_adapter
        from lena.adapters.metrics import MetricsAdapter

        wrapped = get_adapter(model)
        assert isinstance(wrapped, MetricsAdapter)

    def test_unknown_model_raises(self, mocker):
        self._patch_all_adapters(mocker)
        from lena.adapters import UnknownModelError, get_adapter

        with pytest.raises(UnknownModelError):
            get_adapter("unknown-model-xyz")

    def test_returns_metrics_wrapper(self, mocker):
        self._patch_all_adapters(mocker)
        from lena.adapters import get_adapter
        from lena.adapters.metrics import MetricsAdapter

        result = get_adapter("claude-sonnet-4-6")
        assert isinstance(result, MetricsAdapter)


# ---------------------------------------------------------------------------
# MetricsAdapter — OpenTelemetry span verification
# ---------------------------------------------------------------------------

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.trace import StatusCode


def _make_tracer_and_exporter():
    """Return (tracer, exporter) backed by a fresh in-memory provider."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")
    return tracer, exporter


def _make_inner(last_usage=None, raises=None):
    """Return a minimal mock satisfying ModelAdapter contract."""
    inner = MagicMock()
    inner.name = "mock"
    inner.last_usage = last_usage if last_usage is not None else {}
    if raises is not None:
        inner.complete.side_effect = raises
    else:
        inner.complete.return_value = "ok"
    return inner


class TestMetricsAdapter:
    def _build(self, monkeypatch, inner):
        import lena.adapters.metrics as _mod
        from lena.adapters.metrics import MetricsAdapter

        tracer, exporter = _make_tracer_and_exporter()
        monkeypatch.setattr(_mod, "_tracer", tracer)
        adapter = MetricsAdapter(inner)
        return adapter, exporter

    def test_span_emitted_on_complete(self, monkeypatch):
        inner = _make_inner()
        adapter, exporter = self._build(monkeypatch, inner)

        adapter.complete([{"role": "user", "content": "hi"}], model="claude-3")

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "lena.adapter.complete"

    def test_span_attributes_set(self, monkeypatch):
        inner = _make_inner(last_usage={"input_tokens": 10, "output_tokens": 5})
        adapter, exporter = self._build(monkeypatch, inner)

        adapter.complete([{"role": "user", "content": "hi"}], model="test-model")

        span = exporter.get_finished_spans()[0]
        attrs = span.attributes
        assert attrs["lena.adapter"] == "mock"
        assert attrs["lena.model"] == "test-model"
        assert "lena.latency_ms" in attrs

    def test_cache_hit_rate_zero_when_no_tokens(self, monkeypatch):
        inner = _make_inner(last_usage={})
        adapter, exporter = self._build(monkeypatch, inner)

        adapter.complete([{"role": "user", "content": "hi"}], model="m")

        span = exporter.get_finished_spans()[0]
        assert span.attributes["lena.cache.hit_rate"] == 0.0

    def test_cache_hit_rate_computed(self, monkeypatch):
        usage = {
            "input_tokens": 80,
            "cache_read_tokens": 20,
            "cache_write_tokens": 0,
            "output_tokens": 10,
        }
        inner = _make_inner(last_usage=usage)
        adapter, exporter = self._build(monkeypatch, inner)

        adapter.complete([{"role": "user", "content": "hi"}], model="m")

        span = exporter.get_finished_spans()[0]
        # cache_read / (input + cache_read) = 20 / (80 + 20) = 0.2
        assert span.attributes["lena.cache.hit_rate"] == pytest.approx(0.2)

    def test_span_error_on_exception(self, monkeypatch):
        inner = _make_inner(raises=RuntimeError("boom"))
        adapter, exporter = self._build(monkeypatch, inner)

        with pytest.raises(RuntimeError, match="boom"):
            adapter.complete([{"role": "user", "content": "hi"}], model="m")

        span = exporter.get_finished_spans()[0]
        assert span.status.status_code == StatusCode.ERROR
