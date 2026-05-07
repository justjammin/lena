from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from lena.cli import run


def _mock_run_session(return_value=None):
    """Return a pre-wired mock for lena.cli.run_session."""
    mock = MagicMock()
    mock.return_value = return_value or {"upstream_context": "result text"}
    return mock


class TestRunCLI:
    def test_run_with_task_flag(self):
        mock_session = _mock_run_session({"upstream_context": "result text"})
        with patch("lena.cli.run_session", mock_session):
            result = CliRunner().invoke(run, ["--task", "do something"])

        assert result.exit_code == 0
        assert "result text" in result.output

    def test_run_reads_stdin(self):
        mock_session = _mock_run_session({"upstream_context": "result text"})
        with patch("lena.cli.run_session", mock_session):
            result = CliRunner().invoke(run, input="piped task")

        assert result.exit_code == 0

    def test_run_empty_task_exits_nonzero(self):
        result = CliRunner().invoke(run, ["--task", ""])
        assert result.exit_code != 0

    def test_model_override_passed_to_session(self):
        mock_session = _mock_run_session({"upstream_context": ""})
        with patch("lena.cli.run_session", mock_session):
            CliRunner().invoke(run, ["--task", "x", "--model", "gpt-5.5"])

        mock_session.assert_called_once_with("x", config_path=None, model_override="gpt-5.5")
