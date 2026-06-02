from __future__ import annotations

"""Executable tool registry for the agent act/observe loop.

Each callable accepts an ``args`` dict and returns a plain string result.
Exceptions are caught and returned as error strings so the loop can relay
them back to the model without crashing the node.

Safety model for Bash:
    shlex.split + shell=False + timeout. This disables shell pipes, redirects,
    and glob expansion by design.

    Interpreter-escape guard: after peeling leading wrapper binaries (sudo,
    env, nice, …), commands whose unwrapped argv[0] basename — casefolded and
    with any trailing version suffix stripped (python3.12 → python, php8.2 →
    php) — is a known interpreter AND which include an inline-code flag (-c,
    -e, -E, -p, --eval, --print, …) among the remaining tokens are rejected
    before execution. This closes the most common code-injection vectors
    without full containerisation.

    Wrapper-arg parsing is best-effort; see WRAPPERS and _unwrap_argv for the
    precise algorithm and its documented limits.

Path jail for Read / Write / Edit / Grep / Glob:
    Controlled by the module-level ``WORKSPACE_ROOT`` variable.

    By default it is set to the repository root (two levels above this file),
    which enables the jail for all standard deployments.  Override at startup
    by setting the LENA_WORKSPACE_ROOT environment variable or by assigning
    the module-level variable directly.

    Set ``WORKSPACE_ROOT = None`` to disable the jail entirely (single-user /
    fully trusted deployments).

    All path arguments for Read, Write, Edit, Grep, and Glob are resolved to
    absolute realpaths and must fall inside WORKSPACE_ROOT when it is set.
    Path-traversal, absolute out-of-workspace paths, and symlink escapes are
    rejected with a bracketed error string.

    Bash subprocess cwd is also set to WORKSPACE_ROOT when the jail is active.

Security notice:
    See the SECURITY section below for the honest threat model.

SECURITY
--------
a) Bash is remote code execution by design.  The in-process guards in this
   module are best-effort defense-in-depth.  They are NOT a container sandbox.
   A determined adversary who controls the command string can reach arbitrary
   filesystem paths via script-file execution, novel wrapper combinations, or
   other means not covered here.

b) The real trust boundary is manifest opt-in: only agents whose manifest
   explicitly lists Bash, Write, or Edit in their allowed tool set receive
   those tools.  Remove them from untrusted-agent manifests, not here.

c) For UNTRUSTED task input — such as user-supplied prompt content processed
   by an autonomous agent — run the entire harness inside a container, a
   seccomp-filtered process, or a virtual machine.  In-process guards cannot
   substitute for OS-level isolation.

d) Known residual bypasses that are deliberately NOT claimed to be blocked:

   * ``bash script.sh`` — script-file execution.  The jail confines write
     access to the workspace but cannot prevent reading or executing files
     that already exist on the host.  This is by design (builds and tests
     need to run scripts).

   * Flag-glue single-token, e.g. ``python -cCODE`` or ``perl -ECODE``.  The
     glued form is parsed as one shlex token and does not match any entry in
     INLINE_CODE_FLAGS, which only lists the separated flags.  This is a known
     gap for every interpreter; do not claim it is blocked.

   * A novel inline-eval flag on some future interpreter.  INLINE_CODE_FLAGS is
     an explicit enumeration of the inline-code flags for the binaries in
     INTERPRETERS as of this writing (sh/bash/zsh -c, python -c, node -e/-p,
     ruby/perl -e, perl -E, php -r, plus the long forms).  A flag not in that
     set — or an interpreter not in INTERPRETERS — will pass through.

   * Exotic or novel wrapper combinations not covered by the wrapper-strip
     heuristic.  The peeling loop is best-effort; sufficiently obscure
     indirection chains will pass through without triggering the guard.

   * Arbitrary execution of files already inside the workspace.  The jail
     restricts where new files can be written, not what can be run.
"""

import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Callable

_BASH_TIMEOUT = 30  # seconds
_READ_MAX_BYTES = 50_000  # ~50 KB cap to avoid flooding context

# ---------------------------------------------------------------------------
# Security: interpreter-escape guard for Bash
# ---------------------------------------------------------------------------

# Executables that are also interpreters — can run arbitrary code via -c / --eval.
INTERPRETERS: frozenset[str] = frozenset({
    "bash", "sh", "zsh", "fish", "dash",
    "python", "python3",
    "node", "nodejs",
    "ruby", "perl", "php",
})

# Flags that pass inline code to an interpreter as the next (or same) token.
# Covers the inline-eval surface of every binary in INTERPRETERS:
#   sh/bash/zsh/dash  -c / --command
#   python/python3    -c
#   node/nodejs       -e / --eval, -p / --print  (both evaluate a string)
#   ruby              -e
#   perl              -e / -E            (-E enables features but still runs code)
#   php               -r
INLINE_CODE_FLAGS: frozenset[str] = frozenset({
    "-c", "-e", "-E", "-r", "-p",
    "--command", "--eval", "--print",
})

# Wrapper binaries that prefix a real command.  The guard peels these before
# checking whether the true executable is an interpreter.  Parsing is
# best-effort; see _unwrap_argv for details.
WRAPPERS: frozenset[str] = frozenset({
    "env", "sudo", "doas", "nice", "ionice", "nohup", "timeout",
    "stdbuf", "xargs", "command", "setsid", "time", "watch",
})


# Matches a trailing version suffix on a binary basename: "3", "3.12",
# "3.13.1", "20", "8.2".  Used to fold versioned interpreter names
# (python3.12, php8.2, node20) back onto their stem before membership tests.
_VERSION_SUFFIX_RE = re.compile(r"\d+(?:\.\d+)*$")


def _interp_name(token: str) -> str:
    """Return the casefolded basename of *token* with any trailing version
    suffix stripped, for matching against INTERPRETERS.

    Examples:
        ``/usr/bin/python3.12`` → ``python``
        ``PHP8.2``              → ``php``
        ``node20``              → ``node``
        ``nodejs``              → ``nodejs``  (no numeric suffix)
        ``sh``                  → ``sh``

    The suffix is only stripped when the resulting stem is itself a known
    interpreter, so non-interpreter names like ``mp3`` or ``base64`` are left
    untouched.
    """
    base = Path(token).name.casefold()
    if base in INTERPRETERS:
        return base
    stem = _VERSION_SUFFIX_RE.sub("", base)
    if stem != base and stem in INTERPRETERS:
        return stem
    return base


def _unwrap_argv(argv: list[str]) -> list[str]:
    """Peel leading wrapper tokens from *argv*, returning the unwrapped list.

    For each leading token whose casefolded basename is in WRAPPERS the
    function drops that token and any immediate option tokens that follow
    (best-effort heuristic):

    * Tokens starting with ``-`` are always considered options and are dropped.
    * For ``env``, ``NAME=VALUE`` tokens (containing ``=``) are also dropped.
    * For ``timeout``, ``nice``, ``sudo``, ``ionice``, and ``stdbuf`` exactly
      one non-flag argument (e.g. a numeric value or username) is skipped —
      but ONLY if that argument's casefolded basename is not itself in
      INTERPRETERS or WRAPPERS.  This prevents accidentally consuming the
      real command as a "numeric argument."

    This loop terminates as soon as the leading token is no longer a wrapper.
    The original argv list is not modified; a copy is returned.

    IMPORTANT: the caller must execute the ORIGINAL argv, not the unwrapped
    one.  The unwrapped form is used solely for the interpreter check.
    """
    result = list(argv)
    one_arg_wrappers = frozenset({"timeout", "nice", "sudo", "ionice", "stdbuf"})

    while result:
        name = Path(result[0]).name.casefold()
        if name not in WRAPPERS:
            break
        result.pop(0)  # drop the wrapper itself

        # Drop leading option tokens.
        while result and result[0].startswith("-"):
            result.pop(0)

        # For env, also drop NAME=VALUE tokens.
        if name == "env":
            while result and "=" in result[0]:
                result.pop(0)

        # For wrappers that accept a single non-flag positional arg (e.g. a
        # numeric timeout or a username), skip that one argument — but only if
        # it is not itself an interpreter or wrapper name.
        if name in one_arg_wrappers and result:
            candidate = _interp_name(result[0])
            if candidate not in INTERPRETERS and candidate not in WRAPPERS:
                result.pop(0)

    return result


# ---------------------------------------------------------------------------
# Security: workspace path jail
# ---------------------------------------------------------------------------

def _default_workspace_root() -> Path | None:
    """Return the default WORKSPACE_ROOT value for this installation.

    Derived deterministically from this file's location:
    ``lena/runtime/tools.py`` → two ``parents`` up → repo root.

    Overridable at startup via the LENA_WORKSPACE_ROOT environment variable.
    Returns None only when LENA_WORKSPACE_ROOT is explicitly set to an empty
    string, which disables the jail.
    """
    env_override = os.environ.get("LENA_WORKSPACE_ROOT")
    if env_override is not None:
        if env_override == "":
            return None
        return Path(env_override).resolve()
    return Path(__file__).resolve().parents[2]


# Jail is ON by default: set to the repo root derived from __file__.
# Override via LENA_WORKSPACE_ROOT env var or direct assignment.
# Set to None to disable containment entirely.
WORKSPACE_ROOT: Path | None = _default_workspace_root()


def _resolve_in_workspace(raw_path: str) -> Path:
    """Resolve *raw_path* to an absolute realpath.

    When WORKSPACE_ROOT is set, the resolved path must be inside it.
    Raises ValueError with a descriptive message on any escape attempt.
    When WORKSPACE_ROOT is None the jail is disabled and any path is accepted.
    """
    try:
        resolved = Path(raw_path).resolve()
    except Exception as exc:
        raise ValueError(f"cannot resolve path: {exc}") from exc
    if WORKSPACE_ROOT is None:
        return resolved
    root = WORKSPACE_ROOT.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise ValueError(
            f"path escapes workspace: {raw_path!r} resolved to {resolved}, "
            f"which is outside {root}"
        )
    return resolved

# ---------------------------------------------------------------------------
# Tool callables — each (args: dict) -> str
# ---------------------------------------------------------------------------


def _tool_read(args: dict) -> str:
    path = args.get("path", "")
    if not path:
        return "[read error: 'path' argument is required]"
    offset = int(args.get("offset", 0))
    limit = args.get("limit")
    try:
        resolved = _resolve_in_workspace(path)
        text = resolved.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return f"[read error: {exc}]"
    lines = text.splitlines(keepends=True)
    if offset:
        lines = lines[offset:]
    if limit is not None:
        lines = lines[: int(limit)]
    result = "".join(lines)
    if len(result.encode()) > _READ_MAX_BYTES:
        result = result.encode()[:_READ_MAX_BYTES].decode(errors="replace")
        result += f"\n[...truncated at {_READ_MAX_BYTES} bytes]"
    return result


def _tool_write(args: dict) -> str:
    path = args.get("path", "")
    content = args.get("content", "")
    if not path:
        return "[write error: 'path' argument is required]"
    try:
        resolved = _resolve_in_workspace(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return f"[wrote {len(content.encode())} bytes to {path}]"
    except Exception as exc:
        return f"[write error: {exc}]"


def _tool_edit(args: dict) -> str:
    path = args.get("path", "")
    old_string = args.get("old_string", "")
    new_string = args.get("new_string", "")
    if not path:
        return "[edit error: 'path' argument is required]"
    if not old_string:
        return "[edit error: 'old_string' argument is required]"
    try:
        resolved = _resolve_in_workspace(path)
        text = resolved.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return f"[edit error: {exc}]"
    count = text.count(old_string)
    if count == 0:
        return f"[edit error: 'old_string' not found in {path}]"
    if count > 1:
        return f"[edit error: 'old_string' is not unique in {path} ({count} occurrences)]"
    new_text = text.replace(old_string, new_string, 1)
    try:
        resolved.write_text(new_text, encoding="utf-8")
    except Exception as exc:
        return f"[edit error writing file: {exc}]"
    return f"[edited {path}]"


def _tool_bash(args: dict) -> str:
    command = args.get("command", "")
    if not command:
        return "[bash error: 'command' argument is required]"
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        return f"[bash error: could not parse command: {exc}]"
    if not argv:
        return "[bash error: empty command after parsing]"

    # Interpreter-escape guard.
    #
    # 1. Peel leading wrapper binaries (sudo, env, timeout, …) to expose the
    #    real executable.  The original argv is preserved for subprocess.run.
    # 2. Casefold the unwrapped basename before INTERPRETERS membership test.
    # 3. Scan the unwrapped argv[1:] for inline-code flags.
    unwrapped = _unwrap_argv(argv)
    if unwrapped:
        basename = _interp_name(unwrapped[0])
        if basename in INTERPRETERS and any(
            tok in INLINE_CODE_FLAGS for tok in unwrapped[1:]
        ):
            return (
                f"[bash error: interpreter-escape blocked — "
                f"{basename!r} with inline-code flags is not permitted]"
            )

    cwd = WORKSPACE_ROOT if WORKSPACE_ROOT is not None else None
    try:
        proc = subprocess.run(
            argv,
            shell=False,  # intentional: see module docstring
            capture_output=True,
            text=True,
            timeout=_BASH_TIMEOUT,
            cwd=cwd,
        )
        output = proc.stdout + proc.stderr
    except subprocess.TimeoutExpired:
        return f"[bash timeout after {_BASH_TIMEOUT}s]"
    except Exception as exc:
        return f"[bash error: {exc}]"
    if len(output.encode()) > _READ_MAX_BYTES:
        output = output.encode()[:_READ_MAX_BYTES].decode(errors="replace")
        output += f"\n[...truncated at {_READ_MAX_BYTES} bytes]"
    return output


# ---------------------------------------------------------------------------
# Grep / Glob helpers — path arguments run through jail
# ---------------------------------------------------------------------------

def _tool_grep(args: dict) -> str:
    """Run grep -r, rejecting the search path if it escapes the workspace."""
    pattern = args.get("pattern", "")
    raw_path = args.get("path", ".")
    try:
        search_path = _resolve_in_workspace(raw_path)
    except ValueError as exc:
        return f"[grep error: {exc}]"
    return _tool_bash(
        {"command": f"grep -r {shlex.quote(pattern)} {shlex.quote(str(search_path))}"}
    )


def _tool_glob(args: dict) -> str:
    """Run find for a glob pattern, rejecting the search path if it escapes."""
    raw_path = args.get("path", ".")
    glob_pattern = args.get("pattern", "*")
    try:
        search_path = _resolve_in_workspace(raw_path)
    except ValueError as exc:
        return f"[glob error: {exc}]"
    return _tool_bash(
        {"command": f"find {shlex.quote(str(search_path))} -name {shlex.quote(glob_pattern)}"}
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, Callable[[dict], str]] = {
    "Read": _tool_read,
    "Write": _tool_write,
    "Edit": _tool_edit,
    "Bash": _tool_bash,
    "Grep": _tool_grep,
    "Glob": _tool_glob,
}


def execute_tool(name: str, arguments: dict) -> str:
    """Dispatch a tool call by name; return its string result.

    Unknown tool names return a descriptive error string so the model can
    communicate the failure rather than crashing the loop.
    """
    fn = _REGISTRY.get(name)
    if fn is None:
        return f"[unknown tool: {name}]"
    return fn(arguments)


# ---------------------------------------------------------------------------
# OpenAI-style JSON schema builder
# ---------------------------------------------------------------------------

_SCHEMAS: dict[str, dict] = {
    "Read": {
        "name": "Read",
        "description": "Read a file from the filesystem and return its contents.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the file."},
                "offset": {"type": "integer", "description": "Line number to start reading from (0-based)."},
                "limit": {"type": "integer", "description": "Maximum number of lines to return."},
            },
            "required": ["path"],
        },
    },
    "Write": {
        "name": "Write",
        "description": "Write content to a file, creating parent directories as needed.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the file."},
                "content": {"type": "string", "description": "Content to write."},
            },
            "required": ["path", "content"],
        },
    },
    "Edit": {
        "name": "Edit",
        "description": "Perform an exact-match string replacement in a file.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the file."},
                "old_string": {"type": "string", "description": "Exact text to replace (must be unique in the file)."},
                "new_string": {"type": "string", "description": "Replacement text."},
            },
            "required": ["path", "old_string", "new_string"],
        },
    },
    "Bash": {
        "name": "Bash",
        "description": "Execute a shell command. Pipes and redirects are NOT supported (shell=False). Timeout: 30s.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Command to run (no pipes/redirects)."},
            },
            "required": ["command"],
        },
    },
    "Grep": {
        "name": "Grep",
        "description": "Search for a pattern in a directory tree.",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Search pattern."},
                "path": {"type": "string", "description": "Directory to search (default: current directory)."},
            },
            "required": ["pattern"],
        },
    },
    "Glob": {
        "name": "Glob",
        "description": "Find files matching a glob pattern.",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern (e.g. '*.py')."},
                "path": {"type": "string", "description": "Directory to search (default: current directory)."},
            },
            "required": ["pattern"],
        },
    },
}


def build_tool_schema(tool_names: list[str]) -> list[dict]:
    """Return OpenAI-style tool schema dicts for the requested tool names.

    Unknown names are silently skipped. Returns an empty list for empty input.
    """
    result = []
    for name in tool_names:
        schema = _SCHEMAS.get(name)
        if schema is not None:
            result.append({
                "type": "function",
                "function": schema,
            })
    return result
