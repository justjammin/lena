from __future__ import annotations

import shlex
from pathlib import Path
from unittest.mock import patch

import pytest

import lena.runtime.tools as _tools_mod
from lena.runtime.tools import (
    _default_workspace_root,
    _interp_name,
    _tool_bash,
    _tool_edit,
    _tool_glob,
    _tool_grep,
    _tool_read,
    _tool_write,
    _unwrap_argv,
    build_tool_schema,
    execute_tool,
)


# ---------------------------------------------------------------------------
# Autouse fixture: pin WORKSPACE_ROOT to tmp_path for every test in this file.
# This keeps all Read/Write/Edit tests using tmp_path inside the jail, and
# makes the escape-rejection tests predictable regardless of cwd.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_tools_mod, "WORKSPACE_ROOT", tmp_path.resolve())


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


class TestToolRead:
    def test_reads_file(self, tmp_path: Path) -> None:
        f = tmp_path / "hello.txt"
        f.write_text("line1\nline2\nline3\n")
        result = _tool_read({"path": str(f)})
        assert "line1" in result
        assert "line3" in result

    def test_missing_file_returns_error(self, tmp_path: Path) -> None:
        result = _tool_read({"path": str(tmp_path / "nope.txt")})
        assert result.startswith("[read error:")

    def test_offset_and_limit(self, tmp_path: Path) -> None:
        f = tmp_path / "lines.txt"
        f.write_text("a\nb\nc\nd\ne\n")
        result = _tool_read({"path": str(f), "offset": 1, "limit": 2})
        assert "b" in result
        assert "c" in result
        assert "a" not in result
        assert "d" not in result

    def test_missing_path_arg(self) -> None:
        result = _tool_read({})
        assert "path" in result
        assert "required" in result


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------


class TestToolWrite:
    def test_writes_file(self, tmp_path: Path) -> None:
        f = tmp_path / "out.txt"
        result = _tool_write({"path": str(f), "content": "hello"})
        assert "wrote" in result
        assert f.read_text() == "hello"

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        f = tmp_path / "a" / "b" / "c.txt"
        _tool_write({"path": str(f), "content": "nested"})
        assert f.exists()

    def test_missing_path_arg(self) -> None:
        result = _tool_write({"content": "x"})
        assert "path" in result


# ---------------------------------------------------------------------------
# Edit
# ---------------------------------------------------------------------------


class TestToolEdit:
    def test_replaces_unique_string(self, tmp_path: Path) -> None:
        f = tmp_path / "code.py"
        f.write_text("def foo():\n    pass\n")
        result = _tool_edit({"path": str(f), "old_string": "pass", "new_string": "return 1"})
        assert "edited" in result
        assert "return 1" in f.read_text()

    def test_not_found_returns_error(self, tmp_path: Path) -> None:
        f = tmp_path / "f.txt"
        f.write_text("hello")
        result = _tool_edit({"path": str(f), "old_string": "NOTHERE", "new_string": "x"})
        assert "not found" in result

    def test_non_unique_returns_error(self, tmp_path: Path) -> None:
        f = tmp_path / "f.txt"
        f.write_text("aa aa aa")
        result = _tool_edit({"path": str(f), "old_string": "aa", "new_string": "bb"})
        assert "not unique" in result


# ---------------------------------------------------------------------------
# Bash
# ---------------------------------------------------------------------------


class TestToolBash:
    def test_echo(self) -> None:
        result = _tool_bash({"command": "echo hello"})
        assert "hello" in result

    def test_timeout(self) -> None:
        import subprocess
        # Patch timeout to 0.001s and use a command that would block.
        with patch("lena.runtime.tools._BASH_TIMEOUT", 0.001):
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("sleep", 0.001)):
                result = _tool_bash({"command": "sleep 10"})
        assert "timeout" in result

    def test_shell_false_no_pipe_semantics(self) -> None:
        # With shell=False, pipe char is treated as a literal argument, not a pipe.
        # The command "echo a | wc" should either fail (no such file as "|") or
        # pass "a", "|", "wc" as args to echo — it should NOT count lines.
        result = _tool_bash({"command": "echo a | wc"})
        # Either error or output containing "a | wc" literally — not a line count.
        # Key assertion: subprocess.run was called with shell=False.
        import subprocess as sp
        calls: list = []
        original_run = sp.run

        def capture(*args, **kwargs):
            calls.append(kwargs.get("shell", args[1] if len(args) > 1 else None))
            return original_run(*args, **kwargs)

        with patch("subprocess.run", side_effect=capture):
            _tool_bash({"command": "echo hi"})

        # The 'shell' kwarg should be False (or absent, defaulting to False).
        if calls:
            assert calls[0] is False or calls[0] is None

    def test_missing_command_arg(self) -> None:
        result = _tool_bash({})
        assert "required" in result

    def test_empty_command_error(self) -> None:
        result = _tool_bash({"command": ""})
        assert "required" in result


# ---------------------------------------------------------------------------
# execute_tool dispatch
# ---------------------------------------------------------------------------


class TestExecuteTool:
    def test_known_tool_dispatches(self, tmp_path: Path) -> None:
        f = tmp_path / "t.txt"
        f.write_text("content")
        result = execute_tool("Read", {"path": str(f)})
        assert "content" in result

    def test_unknown_tool_returns_error(self) -> None:
        result = execute_tool("FlyingPig", {})
        assert "unknown tool" in result
        assert "FlyingPig" in result

    def test_tool_error_returns_string_not_raise(self, tmp_path: Path) -> None:
        # Read a path that is inside workspace but does not exist — should
        # return error string, not raise.
        missing = str(tmp_path / "__lena_test_nonexistent_xyz__.txt")
        result = execute_tool("Read", {"path": missing})
        assert result.startswith("[")


# ---------------------------------------------------------------------------
# build_tool_schema
# ---------------------------------------------------------------------------


class TestBuildToolSchema:
    def test_empty_returns_empty(self) -> None:
        assert build_tool_schema([]) == []

    def test_unknown_name_skipped(self) -> None:
        result = build_tool_schema(["Read", "Unknown"])
        assert len(result) == 1
        assert result[0]["function"]["name"] == "Read"

    def test_shape(self) -> None:
        result = build_tool_schema(["Read", "Bash"])
        assert len(result) == 2
        for item in result:
            assert item["type"] == "function"
            fn = item["function"]
            assert "name" in fn
            assert "description" in fn
            assert "parameters" in fn
            params = fn["parameters"]
            assert params["type"] == "object"
            assert "properties" in params
            assert "required" in params

    def test_all_manifest_tools(self) -> None:
        # Tools that appear in agents.manifest.yaml should all resolve.
        manifest_tools = ["Read", "Edit", "Write", "Bash", "Grep"]
        result = build_tool_schema(manifest_tools)
        names = {item["function"]["name"] for item in result}
        assert names == set(manifest_tools)


# ---------------------------------------------------------------------------
# Bash interpreter-escape guard
# ---------------------------------------------------------------------------


class TestBashInterpreterEscapeGuard:
    def test_bash_dash_c_rejected(self) -> None:
        result = _tool_bash({"command": "bash -c 'rm -rf /'"})
        assert "interpreter-escape blocked" in result
        assert "bash" in result

    def test_sh_dash_c_rejected(self) -> None:
        result = _tool_bash({"command": "sh -c 'echo pwned'"})
        assert "interpreter-escape blocked" in result

    def test_python_dash_c_rejected(self) -> None:
        result = _tool_bash({"command": "python -c 'import os; os.system(\"id\")'"}  )
        assert "interpreter-escape blocked" in result

    def test_python3_dash_c_rejected(self) -> None:
        result = _tool_bash({"command": "python3 -c 'print(1)'"})
        assert "interpreter-escape blocked" in result

    def test_node_dash_e_rejected(self) -> None:
        result = _tool_bash({"command": "node -e 'console.log(1)'"})
        assert "interpreter-escape blocked" in result

    def test_ruby_dash_e_rejected(self) -> None:
        result = _tool_bash({"command": "ruby -e 'puts 1'"})
        assert "interpreter-escape blocked" in result

    def test_perl_dash_e_rejected(self) -> None:
        result = _tool_bash({"command": "perl -e 'print 1'"})
        assert "interpreter-escape blocked" in result

    def test_php_dash_r_rejected(self) -> None:
        result = _tool_bash({"command": "php -r 'echo 1;'"})
        assert "interpreter-escape blocked" in result

    def test_perl_dash_capital_e_rejected(self) -> None:
        """perl -E runs inline code (with feature bundle) — must be blocked."""
        result = _tool_bash({"command": "perl -E 'say 1'"})
        assert "interpreter-escape blocked" in result

    def test_node_dash_p_rejected(self) -> None:
        """node -p evaluates and prints a string — must be blocked."""
        result = _tool_bash({"command": "node -p '1+1'"})
        assert "interpreter-escape blocked" in result

    def test_node_print_long_rejected(self) -> None:
        """node --print is the long form of -p — must be blocked."""
        result = _tool_bash({"command": "node --print '1+1'"})
        assert "interpreter-escape blocked" in result

    def test_env_node_dash_p_rejected(self) -> None:
        """Wrapper + new inline flag still unwraps and blocks."""
        result = _tool_bash({"command": "env node -p '1+1'"})
        assert "interpreter-escape blocked" in result

    # --- versioned interpreter basenames (python3.12, php8.2, node20) ---

    def test_versioned_python_dash_c_rejected(self) -> None:
        """python3.12 -c must be caught: version suffix folds to 'python'."""
        result = _tool_bash({"command": "python3.12 -c 'print(1)'"})
        assert "interpreter-escape blocked" in result

    def test_versioned_python_minor_dash_c_rejected(self) -> None:
        result = _tool_bash({"command": "python3.13 -c 'x'"})
        assert "interpreter-escape blocked" in result

    def test_versioned_php_dash_r_rejected(self) -> None:
        result = _tool_bash({"command": "php8.2 -r 'echo 1;'"})
        assert "interpreter-escape blocked" in result

    def test_versioned_node_dash_e_rejected(self) -> None:
        result = _tool_bash({"command": "node20 -e '1'"})
        assert "interpreter-escape blocked" in result

    def test_absolute_versioned_python_rejected(self) -> None:
        """/usr/bin/python3.11 -c must be caught (basename + version strip)."""
        result = _tool_bash({"command": "/usr/bin/python3.11 -c 'x'"})
        assert "interpreter-escape blocked" in result

    def test_sudo_versioned_python_rejected(self) -> None:
        """sudo python3.12 -c: version-folded interpreter must not be consumed
        as sudo's positional arg, and must be blocked."""
        result = _tool_bash({"command": "sudo python3.12 -c 'x'"})
        assert "interpreter-escape blocked" in result

    def test_versioned_non_interpreter_not_misfolded(self) -> None:
        """A non-interpreter name with digits (e.g. base64) must NOT be folded
        onto an interpreter stem and must run normally."""
        import subprocess
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                [], 0, stdout="ok\n", stderr=""
            )
            result = _tool_bash({"command": "base64 -w 0 file"})
        assert "interpreter-escape blocked" not in result

    def test_normal_arglist_command_allowed(self, tmp_path: Path) -> None:
        # A plain non-interpreter command must not be blocked.
        result = _tool_bash({"command": "echo hello"})
        assert "hello" in result

    def test_ls_allowed(self, tmp_path: Path) -> None:
        # ls is not an interpreter; no flags from INLINE_CODE_FLAGS.
        result = _tool_bash({"command": f"ls {tmp_path}"})
        assert "interpreter-escape blocked" not in result

    def test_interpreter_without_inline_flag_allowed(self) -> None:
        # python with a script path and no -c / --eval flag — must pass through.
        # We don't actually run python here; just verify the guard doesn't block it.
        # Use a mock to avoid needing a real script file.
        import subprocess
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 0, stdout="ok\n", stderr="")
            result = _tool_bash({"command": "python script.py"})
        assert "interpreter-escape blocked" not in result
        assert "ok" in result

    # --- casefold tests (FIX 2) ---

    def test_bash_uppercase_rejected(self) -> None:
        """BASH -c must be caught despite uppercase basename."""
        result = _tool_bash({"command": "BASH -c 'id'"})
        assert "interpreter-escape blocked" in result

    def test_python_mixed_case_rejected(self) -> None:
        """Python -c must be caught on case-insensitive filesystems."""
        result = _tool_bash({"command": "Python -c 'print(1)'"})
        assert "interpreter-escape blocked" in result

    # --- wrapper-strip tests (FIX 3) ---

    def test_env_bash_dash_c_rejected(self) -> None:
        """env bash -c must be unwrapped and blocked."""
        result = _tool_bash({"command": "env bash -c 'id'"})
        assert "interpreter-escape blocked" in result

    def test_sudo_bash_dash_c_rejected(self) -> None:
        """sudo bash -c must be unwrapped and blocked."""
        result = _tool_bash({"command": "sudo bash -c 'id'"})
        assert "interpreter-escape blocked" in result

    def test_timeout_bash_dash_c_rejected(self) -> None:
        """timeout 5 bash -c must be unwrapped (5 consumed as numeric arg) and blocked."""
        result = _tool_bash({"command": "timeout 5 bash -c 'id'"})
        assert "interpreter-escape blocked" in result

    def test_nice_bash_dash_c_rejected(self) -> None:
        """nice bash -c must be unwrapped and blocked."""
        result = _tool_bash({"command": "nice bash -c 'id'"})
        assert "interpreter-escape blocked" in result

    def test_wrapper_does_not_consume_interpreter_as_arg(self) -> None:
        """sudo bash -c: 'bash' must NOT be consumed as sudo's positional arg."""
        # This is the discriminating test — the guard must see bash, not skip over it.
        result = _tool_bash({"command": "sudo bash -c 'id'"})
        assert "interpreter-escape blocked" in result

    # --- residual: bash script.sh is allowed by design (FIX 6 documented residual) ---

    def test_bash_script_file_not_blocked(self) -> None:
        """bash script.sh (no -c) is a known residual — must NOT be blocked.

        The jail confines new writes to the workspace but cannot prevent running
        scripts that already exist.  This test proves we do not overclaim.
        """
        import subprocess
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                [], 0, stdout="ran\n", stderr=""
            )
            result = _tool_bash({"command": "bash script.sh"})
        assert "interpreter-escape blocked" not in result


# ---------------------------------------------------------------------------
# Workspace path jail
# ---------------------------------------------------------------------------


class TestWorkspacePathJail:
    def test_read_inside_workspace_succeeds(self, tmp_path: Path) -> None:
        f = tmp_path / "safe.txt"
        f.write_text("safe content")
        result = _tool_read({"path": str(f)})
        assert "safe content" in result

    def test_write_inside_workspace_succeeds(self, tmp_path: Path) -> None:
        f = tmp_path / "output.txt"
        result = _tool_write({"path": str(f), "content": "written"})
        assert "wrote" in result
        assert f.read_text() == "written"

    def test_edit_inside_workspace_succeeds(self, tmp_path: Path) -> None:
        f = tmp_path / "edit_me.txt"
        f.write_text("old text")
        result = _tool_edit({"path": str(f), "old_string": "old text", "new_string": "new text"})
        assert "edited" in result
        assert f.read_text() == "new text"

    def test_read_absolute_escape_rejected(self) -> None:
        result = _tool_read({"path": "/etc/passwd"})
        assert "escapes workspace" in result or result.startswith("[read error:")

    def test_write_absolute_escape_rejected(self) -> None:
        result = _tool_write({"path": "/tmp/lena_escape_test.txt", "content": "bad"})
        assert "escapes workspace" in result or result.startswith("[write error:")

    def test_edit_absolute_escape_rejected(self) -> None:
        result = _tool_edit({"path": "/etc/hosts", "old_string": "localhost", "new_string": "pwned"})
        assert "escapes workspace" in result or result.startswith("[edit error:")

    def test_read_dotdot_traversal_rejected(self, tmp_path: Path) -> None:
        # Construct a path that tries to escape via ../..
        escape = str(tmp_path / ".." / ".." / "outside.txt")
        result = _tool_read({"path": escape})
        assert "escapes workspace" in result or result.startswith("[read error:")

    def test_write_dotdot_traversal_rejected(self, tmp_path: Path) -> None:
        escape = str(tmp_path / ".." / ".." / "escape.txt")
        result = _tool_write({"path": escape, "content": "bad"})
        assert "escapes workspace" in result or result.startswith("[write error:")


# ---------------------------------------------------------------------------
# Jail ON by default (FIX 1)
# ---------------------------------------------------------------------------


class TestJailOnByDefault:
    def test_default_workspace_root_is_repo_root(self) -> None:
        """_default_workspace_root() must return the repo root, not None."""
        root = _default_workspace_root()
        assert root is not None
        # Repo root should contain lena/ subdirectory.
        assert (root / "lena").is_dir(), f"Expected lena/ under {root}"

    def test_default_workspace_root_equals_parents_2_of_file(self) -> None:
        """Deterministic derivation: two parents up from tools.py."""
        import lena.runtime.tools as mod
        expected = Path(mod.__file__).resolve().parents[2]
        assert _default_workspace_root() == expected

    def test_write_outside_default_root_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """With real default root active, writing to /etc/x must be rejected."""
        real_root = _default_workspace_root()
        monkeypatch.setattr(_tools_mod, "WORKSPACE_ROOT", real_root)
        result = _tool_write({"path": "/etc/lena_jail_test_x", "content": "bad"})
        assert "escapes workspace" in result or result.startswith("[write error:")

    def test_read_outside_default_root_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """With real default root active, reading /etc/passwd must be rejected."""
        real_root = _default_workspace_root()
        monkeypatch.setattr(_tools_mod, "WORKSPACE_ROOT", real_root)
        result = _tool_read({"path": "/etc/passwd"})
        assert "escapes workspace" in result or result.startswith("[read error:")


# ---------------------------------------------------------------------------
# Grep / Glob path jail (FIX 4)
# ---------------------------------------------------------------------------


class TestGrepGlobJail:
    def test_grep_inside_workspace_succeeds(self, tmp_path: Path) -> None:
        f = tmp_path / "haystack.txt"
        f.write_text("needle in a haystack\n")
        result = _tool_grep({"pattern": "needle", "path": str(tmp_path)})
        assert "grep error" not in result

    def test_grep_outside_workspace_rejected(self) -> None:
        result = _tool_grep({"pattern": "root", "path": "/etc"})
        assert "grep error" in result
        assert "escapes workspace" in result

    def test_glob_inside_workspace_succeeds(self, tmp_path: Path) -> None:
        (tmp_path / "file.py").write_text("")
        result = _tool_glob({"pattern": "*.py", "path": str(tmp_path)})
        assert "glob error" not in result

    def test_glob_outside_workspace_rejected(self) -> None:
        result = _tool_glob({"pattern": "*.conf", "path": "/etc"})
        assert "glob error" in result
        assert "escapes workspace" in result


# ---------------------------------------------------------------------------
# _unwrap_argv unit tests (FIX 3 internals)
# ---------------------------------------------------------------------------


class TestUnwrapArgv:
    def test_no_wrapper_unchanged(self) -> None:
        assert _unwrap_argv(["bash", "-c", "id"]) == ["bash", "-c", "id"]

    def test_env_peeled(self) -> None:
        result = _unwrap_argv(["env", "bash", "-c", "id"])
        assert result == ["bash", "-c", "id"]

    def test_env_with_var_peeled(self) -> None:
        result = _unwrap_argv(["env", "FOO=bar", "bash", "-c", "id"])
        assert result == ["bash", "-c", "id"]

    def test_sudo_peeled(self) -> None:
        result = _unwrap_argv(["sudo", "bash", "-c", "id"])
        assert result == ["bash", "-c", "id"]

    def test_timeout_numeric_arg_consumed(self) -> None:
        result = _unwrap_argv(["timeout", "5", "bash", "-c", "id"])
        assert result == ["bash", "-c", "id"]

    def test_nice_peeled(self) -> None:
        result = _unwrap_argv(["nice", "bash", "-c", "id"])
        assert result == ["bash", "-c", "id"]

    def test_wrapper_does_not_consume_interpreter(self) -> None:
        """sudo bash -c: 'bash' must remain after peeling sudo."""
        result = _unwrap_argv(["sudo", "bash", "-c", "id"])
        assert result[0].casefold() == "bash"

    def test_empty_argv_returns_empty(self) -> None:
        assert _unwrap_argv([]) == []

    def test_chained_wrappers_peeled(self) -> None:
        """env sudo bash -c: both env and sudo stripped."""
        result = _unwrap_argv(["env", "sudo", "bash", "-c", "id"])
        assert result[0].casefold() == "bash"

    def test_sudo_does_not_consume_versioned_interpreter(self) -> None:
        """sudo python3.12 -c: 'python3.12' must survive the positional skip."""
        result = _unwrap_argv(["sudo", "python3.12", "-c", "x"])
        assert result[0] == "python3.12"


class TestInterpName:
    def test_plain_interpreter_unchanged(self) -> None:
        assert _interp_name("bash") == "bash"
        assert _interp_name("python") == "python"

    def test_path_stripped(self) -> None:
        # python3 is itself in INTERPRETERS, so it matches directly (no fold).
        assert _interp_name("/usr/bin/python3") == "python3"
        assert _interp_name("/usr/local/bin/bash") == "bash"

    def test_version_suffix_folded(self) -> None:
        assert _interp_name("python3.12") == "python"
        assert _interp_name("php8.2") == "php"
        assert _interp_name("node20") == "node"

    def test_casefolded(self) -> None:
        assert _interp_name("PYTHON3.12") == "python"
        assert _interp_name("BASH") == "bash"

    def test_non_interpreter_not_folded(self) -> None:
        # No interpreter stem — returned as-is, not collapsed.
        assert _interp_name("base64") == "base64"
        assert _interp_name("mp3") == "mp3"
        assert _interp_name("pythonista") == "pythonista"

    def test_nodejs_no_suffix(self) -> None:
        assert _interp_name("nodejs") == "nodejs"
