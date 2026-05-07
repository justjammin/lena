"""Tests for HandoffTransformer — token cap, header, last assistant turn preservation."""
from __future__ import annotations

import pytest

from lena.runtime.handoff import HandoffTransformer, _HEADER


class TestHandoffTransformer:
    def test_header_always_present(self):
        t = HandoffTransformer(cap=500)
        result = t.compress([], None)
        assert result.startswith(_HEADER)

    def test_empty_messages_no_crash(self):
        t = HandoffTransformer(cap=500)
        result = t.compress([], None)
        assert isinstance(result, str)

    def test_last_assistant_turn_preserved(self):
        t = HandoffTransformer(cap=500)
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "I am the last assistant turn"},
        ]
        result = t.compress(messages, None)
        assert "I am the last assistant turn" in result

    def test_last_assistant_preserved_even_when_others_truncated(self):
        """Fill budget with many messages — last assistant must still appear."""
        t = HandoffTransformer(cap=50)  # tiny cap
        filler = [
            {"role": "user", "content": "x" * 200},
            {"role": "assistant", "content": "y" * 200},
            {"role": "user", "content": "z" * 200},
            {"role": "assistant", "content": "LAST_ASSISTANT_CONTENT"},
        ]
        result = t.compress(filler, None)
        assert "LAST_ASSISTANT_CONTENT" in result

    def test_token_cap_enforced(self):
        """Non-last-assistant content should be dropped when over cap."""
        t = HandoffTransformer(cap=30)  # tiny cap
        messages = [
            # These user messages should be dropped — they push over budget
            {"role": "user", "content": "SHOULD_BE_DROPPED " * 200},
            {"role": "user", "content": "ALSO_DROPPED " * 200},
            {"role": "assistant", "content": "short last turn"},
        ]
        result = t.compress(messages, None)
        # Dropped messages must not appear
        assert "SHOULD_BE_DROPPED" not in result
        assert "ALSO_DROPPED" not in result
        # Last assistant always present
        assert "short last turn" in result

    def test_prior_output_injected(self):
        t = HandoffTransformer(cap=500)
        result = t.compress([], prior_output="PRIOR_STEP_OUTPUT")
        assert "PRIOR_STEP_OUTPUT" in result

    def test_block_content_handled(self):
        """Anthropic block-format content should not crash the transformer."""
        t = HandoffTransformer(cap=500)
        messages = [
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "block content here"},
                ],
            }
        ]
        result = t.compress(messages, None)
        assert "block content here" in result

    def test_returns_string(self):
        t = HandoffTransformer(cap=200)
        messages = [
            {"role": "user", "content": "task"},
            {"role": "assistant", "content": "response"},
        ]
        result = t.compress(messages, None)
        assert isinstance(result, str)
        assert len(result) > 0
