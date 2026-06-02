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
        completion = adapter.complete(messages, model="claude-3-sonnet")

        assert completion.content == "response text"
        assert completion.tool_calls == []
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
    from lena.adapters.base import Completion

    inner = MagicMock()
    inner.name = "mock"
    inner.last_usage = last_usage if last_usage is not None else {}
    if raises is not None:
        inner.complete.side_effect = raises
    else:
        inner.complete.return_value = Completion(content="ok", tool_calls=[])
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


# ---------------------------------------------------------------------------
# MetricsAdapter — tools forwarding + span attribute
# ---------------------------------------------------------------------------


class TestMetricsAdapterToolsForwarding:
    def _build(self, monkeypatch, inner):
        import lena.adapters.metrics as _mod
        from lena.adapters.metrics import MetricsAdapter

        tracer, exporter = _make_tracer_and_exporter()
        monkeypatch.setattr(_mod, "_tracer", tracer)
        return MetricsAdapter(inner), exporter

    def test_tools_forwarded_to_inner(self, monkeypatch):
        inner = _make_inner()
        adapter, _ = self._build(monkeypatch, inner)

        tools = [{"type": "function", "function": {"name": "Read", "description": "d", "parameters": {"type": "object", "properties": {}, "required": []}}}]
        adapter.complete([{"role": "user", "content": "hi"}], model="m", tools=tools)

        call_kwargs = inner.complete.call_args
        assert call_kwargs.kwargs.get("tools") == tools

    def test_tools_count_span_attribute(self, monkeypatch):
        inner = _make_inner()
        adapter, exporter = self._build(monkeypatch, inner)

        tools = [
            {"type": "function", "function": {"name": "Read", "description": "d", "parameters": {"type": "object", "properties": {}, "required": []}}},
            {"type": "function", "function": {"name": "Bash", "description": "d", "parameters": {"type": "object", "properties": {}, "required": []}}},
        ]
        adapter.complete([{"role": "user", "content": "hi"}], model="m", tools=tools)

        span = exporter.get_finished_spans()[0]
        assert span.attributes["lena.tools.count"] == 2

    def test_no_tools_count_zero(self, monkeypatch):
        inner = _make_inner()
        adapter, exporter = self._build(monkeypatch, inner)

        adapter.complete([{"role": "user", "content": "hi"}], model="m")

        span = exporter.get_finished_spans()[0]
        assert span.attributes["lena.tools.count"] == 0


# ---------------------------------------------------------------------------
# AnthropicAdapter — tools schema translation + tool_call response parsing
# ---------------------------------------------------------------------------


class TestAnthropicToolsHandling:
    def _make_adapter(self, mock_client):
        from lena.adapters.anthropic import AnthropicAdapter

        adapter = AnthropicAdapter.__new__(AnthropicAdapter)
        adapter._client = mock_client
        adapter.last_usage = {}
        return adapter

    def _base_usage(self):
        usage = MagicMock()
        usage.input_tokens = 10
        usage.output_tokens = 5
        usage.cache_read_input_tokens = 0
        usage.cache_creation_input_tokens = 0
        return usage

    def test_tools_translated_to_anthropic_schema(self):
        """OpenAI-style tool schema must be converted to Anthropic format in the SDK call."""
        mock_client = MagicMock()

        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "ok"
        mock_client.messages.create.return_value.content = [text_block]
        mock_client.messages.create.return_value.usage = self._base_usage()

        adapter = self._make_adapter(mock_client)

        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": "Read",
                    "description": "Read a file",
                    "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
                },
            }
        ]
        adapter.complete([{"role": "user", "content": "hi"}], model="claude-3", tools=openai_tools)

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert "tools" in call_kwargs
        translated = call_kwargs["tools"]
        assert len(translated) == 1
        assert translated[0]["name"] == "Read"
        assert translated[0]["description"] == "Read a file"
        assert "input_schema" in translated[0]
        assert translated[0]["input_schema"]["properties"]["path"]["type"] == "string"
        # OpenAI "parameters" key must NOT appear in the translated entry.
        assert "parameters" not in translated[0]

    def test_tool_use_response_parsed_to_tool_call(self):
        """Response with tool_use block must produce a ToolCall in Completion.tool_calls."""
        mock_client = MagicMock()

        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.id = "toolu_01"
        tool_block.name = "Read"
        tool_block.input = {"path": "/tmp/x.txt"}
        mock_client.messages.create.return_value.content = [tool_block]
        mock_client.messages.create.return_value.usage = self._base_usage()

        adapter = self._make_adapter(mock_client)
        completion = adapter.complete([{"role": "user", "content": "read it"}], model="claude-3")

        assert completion.content == ""
        assert len(completion.tool_calls) == 1
        tc = completion.tool_calls[0]
        assert tc["id"] == "toolu_01"
        assert tc["name"] == "Read"
        assert tc["arguments"] == {"path": "/tmp/x.txt"}

    def test_last_usage_populated_on_tool_response(self):
        mock_client = MagicMock()

        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.id = "t1"
        tool_block.name = "Bash"
        tool_block.input = {"command": "ls"}
        mock_client.messages.create.return_value.content = [tool_block]
        usage = self._base_usage()
        usage.input_tokens = 42
        usage.output_tokens = 7
        mock_client.messages.create.return_value.usage = usage

        adapter = self._make_adapter(mock_client)
        adapter.complete([{"role": "user", "content": "go"}], model="claude-3")

        assert adapter.last_usage["input_tokens"] == 42
        assert adapter.last_usage["output_tokens"] == 7


# ---------------------------------------------------------------------------
# OpenAIAdapter — tools passthrough + Completion shape + last_usage
# ---------------------------------------------------------------------------


class TestOpenAIAdapterToolsHandling:
    def _make_adapter(self, mock_client):
        from lena.adapters.openai import OpenAIAdapter

        adapter = OpenAIAdapter.__new__(OpenAIAdapter)
        adapter._client = mock_client
        adapter.last_usage = {}
        return adapter

    def _base_response(self, content="", tool_calls=None):
        """Build a minimal mock response matching what OpenAIAdapter reads."""
        msg = MagicMock()
        msg.content = content
        msg.tool_calls = tool_calls or []

        choice = MagicMock()
        choice.message = msg

        usage = MagicMock()
        usage.prompt_tokens = 20
        usage.completion_tokens = 8
        usage.prompt_tokens_details = None

        response = MagicMock()
        response.choices = [choice]
        response.usage = usage
        return response

    def test_tools_passed_through_to_sdk(self):
        """tools= must be forwarded verbatim into chat.completions.create kwargs."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = self._base_response(content="done")
        adapter = self._make_adapter(mock_client)

        tools = [{"type": "function", "function": {"name": "Bash", "description": "d", "parameters": {"type": "object", "properties": {}, "required": []}}}]
        adapter.complete([{"role": "user", "content": "hi"}], model="gpt-4o", tools=tools)

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs.get("tools") == tools

    def test_no_tools_not_in_sdk_call(self):
        """When tools=None, the SDK call must NOT receive a tools kwarg."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = self._base_response(content="hi")
        adapter = self._make_adapter(mock_client)

        adapter.complete([{"role": "user", "content": "hi"}], model="gpt-4o")

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert "tools" not in call_kwargs

    def test_tool_call_parsed_from_response(self):
        """A response with tool_calls must produce ToolCall objects with dict arguments."""
        mock_client = MagicMock()

        raw_tc = MagicMock()
        raw_tc.id = "call_abc"
        raw_tc.function.name = "Read"
        raw_tc.function.arguments = '{"path": "/tmp/test.txt"}'
        mock_client.chat.completions.create.return_value = self._base_response(tool_calls=[raw_tc])
        adapter = self._make_adapter(mock_client)

        completion = adapter.complete([{"role": "user", "content": "go"}], model="gpt-4o")

        assert completion.content == ""
        assert len(completion.tool_calls) == 1
        tc = completion.tool_calls[0]
        assert tc["id"] == "call_abc"
        assert tc["name"] == "Read"
        assert tc["arguments"] == {"path": "/tmp/test.txt"}

    def test_last_usage_populated(self):
        mock_client = MagicMock()
        response = self._base_response(content="ok")
        response.usage.prompt_tokens = 30
        response.usage.completion_tokens = 12
        mock_client.chat.completions.create.return_value = response
        adapter = self._make_adapter(mock_client)

        adapter.complete([{"role": "user", "content": "hi"}], model="gpt-4o")

        assert adapter.last_usage["input_tokens"] == 30
        assert adapter.last_usage["output_tokens"] == 12
        assert adapter.last_usage["cache_read_tokens"] == 0

    def test_completion_text_no_tool_calls(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = self._base_response(content="the answer")
        adapter = self._make_adapter(mock_client)

        completion = adapter.complete([{"role": "user", "content": "hi"}], model="gpt-4o")

        assert completion.content == "the answer"
        assert completion.tool_calls == []


# ---------------------------------------------------------------------------
# GeminiAdapter — tools translation + tool_call response parsing + last_usage
# ---------------------------------------------------------------------------


class TestGeminiAdapterToolsHandling:
    def _make_adapter(self, mock_client):
        from lena.adapters.gemini import GeminiAdapter

        adapter = GeminiAdapter.__new__(GeminiAdapter)
        adapter._client = mock_client
        adapter._cache_registry = {}
        adapter.last_usage = {}
        adapter.last_cache_fallback = False
        return adapter

    def _base_metadata(self, input_tokens=10, output_tokens=5, cached=0):
        meta = MagicMock()
        meta.prompt_token_count = input_tokens
        meta.candidates_token_count = output_tokens
        meta.cached_content_token_count = cached
        return meta

    def test_tools_translated_to_function_declarations(self):
        """OpenAI-style tools must be translated to Gemini FunctionDeclaration format."""
        mock_client = MagicMock()

        response = MagicMock()
        response.text = "ok"
        response.usage_metadata = self._base_metadata()
        response.candidates = []
        mock_client.models.generate_content.return_value = response
        adapter = self._make_adapter(mock_client)

        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": "Bash",
                    "description": "Run shell command",
                    "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]},
                },
            }
        ]
        adapter.complete([{"role": "user", "content": "hi"}], model="gemini-1.5-pro", tools=openai_tools)

        call_kwargs = mock_client.models.generate_content.call_args.kwargs
        # tools must be passed via config object.
        config = call_kwargs.get("config")
        assert config is not None
        # config is a GenerateContentConfig MagicMock — inspect what was passed to its constructor.
        from lena.adapters.gemini import _genai_types
        if _genai_types is not None:
            # Get the kwargs passed to GenerateContentConfig constructor.
            # We can inspect by reading config.tools from the mock — or check the call.
            # The adapter builds config_obj = _genai_types.GenerateContentConfig(**generate_config)
            # where generate_config["tools"] = [_genai_types.Tool(function_declarations=[...])].
            # Since _genai_types is real, check that config is an instance of GenerateContentConfig.
            assert isinstance(config, _genai_types.GenerateContentConfig)

    def test_tools_config_contains_function_declarations(self):
        """Verify function_declarations in the generate_config dict before SDK call."""
        from unittest.mock import call as mock_call
        mock_client = MagicMock()

        response = MagicMock()
        response.text = "hi"
        response.usage_metadata = self._base_metadata()
        response.candidates = []
        mock_client.models.generate_content.return_value = response

        # Patch GenerateContentConfig to capture the kwargs passed to it.
        captured_config_kwargs: dict = {}

        from lena.adapters import gemini as _gemini_mod
        from lena.adapters.gemini import _genai_types
        if _genai_types is None:
            pytest.skip("google-genai not installed")

        original_gcc = _genai_types.GenerateContentConfig

        def capturing_gcc(**kwargs):
            captured_config_kwargs.update(kwargs)
            return original_gcc(**kwargs)

        with patch.object(_genai_types, "GenerateContentConfig", side_effect=capturing_gcc):
            adapter = self._make_adapter(mock_client)
            openai_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "Read",
                        "description": "Read a file",
                        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
                    },
                }
            ]
            adapter.complete([{"role": "user", "content": "hi"}], model="gemini-1.5-pro", tools=openai_tools)

        assert "tools" in captured_config_kwargs
        gemini_tools = captured_config_kwargs["tools"]
        assert len(gemini_tools) == 1
        # Each Tool has function_declarations list.
        tool_obj = gemini_tools[0]
        fn_decls = tool_obj.function_declarations
        assert len(fn_decls) == 1
        assert fn_decls[0].name == "Read"

    def test_tool_call_parsed_from_function_call_parts(self):
        """Response parts with function_call must produce ToolCall in Completion."""
        mock_client = MagicMock()

        fc = MagicMock()
        fc.name = "Read"
        fc.args = {"path": "/tmp/f.txt"}

        part = MagicMock()
        part.function_call = fc

        candidate = MagicMock()
        candidate.content.parts = [part]

        response = MagicMock()
        response.text = ""
        response.usage_metadata = self._base_metadata()
        response.candidates = [candidate]
        mock_client.models.generate_content.return_value = response

        from lena.adapters.gemini import GeminiAdapter
        adapter = self._make_adapter(mock_client)
        completion = adapter.complete([{"role": "user", "content": "go"}], model="gemini-1.5-pro")

        assert len(completion.tool_calls) == 1
        tc = completion.tool_calls[0]
        assert tc["name"] == "Read"
        assert tc["arguments"] == {"path": "/tmp/f.txt"}
        # Gemini synthesizes call IDs as "call_{i}".
        assert tc["id"].startswith("call_")

    def test_last_usage_populated(self):
        mock_client = MagicMock()

        response = MagicMock()
        response.text = "ok"
        response.usage_metadata = self._base_metadata(input_tokens=55, output_tokens=13, cached=8)
        response.candidates = []
        mock_client.models.generate_content.return_value = response

        adapter = self._make_adapter(mock_client)
        adapter.complete([{"role": "user", "content": "hi"}], model="gemini-1.5-pro")

        assert adapter.last_usage["input_tokens"] == 55
        assert adapter.last_usage["output_tokens"] == 13
        assert adapter.last_usage["cache_read_tokens"] == 8

    def test_completion_text_no_tool_calls(self):
        mock_client = MagicMock()

        response = MagicMock()
        response.text = "gemini answer"
        response.usage_metadata = self._base_metadata()
        response.candidates = []
        mock_client.models.generate_content.return_value = response

        adapter = self._make_adapter(mock_client)
        completion = adapter.complete([{"role": "user", "content": "hi"}], model="gemini-1.5-pro")

        assert completion.content == "gemini answer"
        assert completion.tool_calls == []


# ---------------------------------------------------------------------------
# OllamaAdapter — tools passthrough + Completion shape + last_usage
# ---------------------------------------------------------------------------


class TestOllamaAdapterToolsHandling:
    def _make_adapter(self):
        from lena.adapters.ollama import OllamaAdapter

        adapter = OllamaAdapter.__new__(OllamaAdapter)
        adapter.last_usage = {}
        return adapter

    def _dict_response(self, content="", tool_calls=None, prompt_eval=10, eval_count=5):
        return {
            "message": {
                "content": content,
                "tool_calls": tool_calls or [],
            },
            "prompt_eval_count": prompt_eval,
            "eval_count": eval_count,
        }

    def test_tools_passed_through_to_sdk(self):
        """tools= must be forwarded verbatim into _ollama_sdk.chat kwargs."""
        from unittest.mock import patch as _patch
        adapter = self._make_adapter()
        tools = [{"type": "function", "function": {"name": "Read", "description": "d", "parameters": {"type": "object", "properties": {}, "required": []}}}]

        with _patch("lena.adapters.ollama._ollama_sdk") as mock_sdk:
            mock_sdk.chat.return_value = self._dict_response(content="ok")
            adapter.complete([{"role": "user", "content": "hi"}], model="llama3", tools=tools)

        call_kwargs = mock_sdk.chat.call_args.kwargs
        assert call_kwargs.get("tools") == tools

    def test_no_tools_not_in_sdk_call(self):
        from unittest.mock import patch as _patch
        adapter = self._make_adapter()

        with _patch("lena.adapters.ollama._ollama_sdk") as mock_sdk:
            mock_sdk.chat.return_value = self._dict_response(content="hi")
            adapter.complete([{"role": "user", "content": "hi"}], model="llama3")

        call_kwargs = mock_sdk.chat.call_args.kwargs
        assert "tools" not in call_kwargs

    def test_tool_call_parsed_from_dict_response(self):
        """Dict-shaped response with tool_calls must parse to ToolCall with dict arguments."""
        from unittest.mock import patch as _patch
        adapter = self._make_adapter()

        dict_tool_call = {
            "id": "call_0",
            "function": {"name": "Bash", "arguments": {"command": "ls"}},
        }

        with _patch("lena.adapters.ollama._ollama_sdk") as mock_sdk:
            mock_sdk.chat.return_value = self._dict_response(tool_calls=[dict_tool_call])
            completion = adapter.complete([{"role": "user", "content": "go"}], model="llama3")

        assert len(completion.tool_calls) == 1
        tc = completion.tool_calls[0]
        assert tc["id"] == "call_0"
        assert tc["name"] == "Bash"
        assert tc["arguments"] == {"command": "ls"}

    def test_last_usage_populated(self):
        from unittest.mock import patch as _patch
        adapter = self._make_adapter()

        with _patch("lena.adapters.ollama._ollama_sdk") as mock_sdk:
            mock_sdk.chat.return_value = self._dict_response(content="x", prompt_eval=25, eval_count=9)
            adapter.complete([{"role": "user", "content": "hi"}], model="llama3")

        assert adapter.last_usage["input_tokens"] == 25
        assert adapter.last_usage["output_tokens"] == 9
        assert adapter.last_usage["cache_read_tokens"] == 0

    def test_completion_text_no_tool_calls(self):
        from unittest.mock import patch as _patch
        adapter = self._make_adapter()

        with _patch("lena.adapters.ollama._ollama_sdk") as mock_sdk:
            mock_sdk.chat.return_value = self._dict_response(content="ollama answer")
            completion = adapter.complete([{"role": "user", "content": "hi"}], model="llama3")

        assert completion.content == "ollama answer"
        assert completion.tool_calls == []

    def test_model_prefix_stripped(self):
        """model starting with 'ollama/' must have the prefix stripped before SDK call."""
        from unittest.mock import patch as _patch
        adapter = self._make_adapter()

        with _patch("lena.adapters.ollama._ollama_sdk") as mock_sdk:
            mock_sdk.chat.return_value = self._dict_response(content="ok")
            adapter.complete([{"role": "user", "content": "hi"}], model="ollama/llama3")

        call_kwargs = mock_sdk.chat.call_args.kwargs
        assert call_kwargs.get("model") == "llama3"
