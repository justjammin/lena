#!/bin/bash
# lena — one-command hook installer for Claude Code
# Installs: SessionStart hook (auto-loads LENA orchestration rules each session)
# Usage: bash hooks/install.sh
#   or:  bash <(curl -s https://raw.githubusercontent.com/justjammin/lena/main/hooks/install.sh)
#   or:  bash hooks/install.sh --force   (re-install over existing hooks)
set -e

FORCE=0
for arg in "$@"; do
  case "$arg" in
    --force|-f) FORCE=1 ;;
  esac
done

# Detect Windows (Git Bash / MSYS / MINGW) — not WSL (WSL reports "linux-gnu")
case "$OSTYPE" in
  msys*|cygwin*|mingw*)
    echo "WARNING: Running on Windows ($OSTYPE)."
    echo "         This script works in Git Bash/MSYS but symlinks may require"
    echo "         Developer Mode or admin privileges."
    echo "         If you installed via 'claude plugin install', you don't need this script."
    echo ""
    ;;
esac

# Require node — used to merge hook config into settings.json safely
if ! command -v node >/dev/null 2>&1; then
  echo "ERROR: 'node' is required to install the LENA hooks (used to merge"
  echo "       the hook config into ~/.claude/settings.json safely)."
  echo "       Install Node.js from https://nodejs.org and re-run this script."
  exit 1
fi

CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
HOOKS_DIR="$CLAUDE_DIR/hooks"
SKILLS_DIR="$CLAUDE_DIR/skills/lena"
SETTINGS="$CLAUDE_DIR/settings.json"
REPO_RAW="https://raw.githubusercontent.com/justjammin/lena/main"

HOOK_FILES=("lena-activate.js" "package.json")

# Resolve source — works from repo clone or curl pipe
SCRIPT_DIR=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
fi

# Determine repo root (one level up from hooks/)
REPO_ROOT=""
if [ -n "$SCRIPT_DIR" ]; then
  REPO_ROOT="$(cd "$SCRIPT_DIR/.." 2>/dev/null && pwd)"
fi

# Check if already installed (unless --force)
ALREADY_INSTALLED=0
if [ "$FORCE" -eq 0 ]; then
  ALL_FILES_PRESENT=1
  for hook in "${HOOK_FILES[@]}"; do
    if [ ! -f "$HOOKS_DIR/$hook" ]; then
      ALL_FILES_PRESENT=0
      break
    fi
  done

  if [ ! -f "$SKILLS_DIR/SKILL.md" ]; then
    ALL_FILES_PRESENT=0
  fi

  HOOK_WIRED=0
  if [ "$ALL_FILES_PRESENT" -eq 1 ] && [ -f "$SETTINGS" ]; then
    if LENA_SETTINGS="$SETTINGS" node -e "
      const fs = require('fs');
      const settings = JSON.parse(fs.readFileSync(process.env.LENA_SETTINGS, 'utf8'));
      const hasHook = Array.isArray(settings.hooks?.SessionStart) &&
        settings.hooks.SessionStart.some(e =>
          e.hooks && e.hooks.some(h => h.command && h.command.includes('lena-activate.js'))
        );
      process.exit(hasHook ? 0 : 1);
    " >/dev/null 2>&1; then
      HOOK_WIRED=1
    fi
  fi

  if [ "$ALL_FILES_PRESENT" -eq 1 ] && [ "$HOOK_WIRED" -eq 1 ]; then
    ALREADY_INSTALLED=1
    echo "LENA hooks already installed in $HOOKS_DIR"
    echo "  Re-run with --force to overwrite: bash hooks/install.sh --force"
    echo ""
  fi
fi

if [ "$ALREADY_INSTALLED" -eq 1 ] && [ "$FORCE" -eq 0 ]; then
  echo "Nothing to do. Hooks are already in place."
  exit 0
fi

if [ "$FORCE" -eq 1 ] && [ -f "$HOOKS_DIR/lena-activate.js" ]; then
  echo "Reinstalling LENA hooks (--force)..."
else
  echo "Installing LENA hooks..."
fi

# 1. Ensure directories exist
mkdir -p "$HOOKS_DIR"
mkdir -p "$SKILLS_DIR"

# 2. Copy or download hook files
for hook in "${HOOK_FILES[@]}"; do
  if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/$hook" ]; then
    cp "$SCRIPT_DIR/$hook" "$HOOKS_DIR/$hook"
  else
    curl -fsSL "$REPO_RAW/hooks/$hook" -o "$HOOKS_DIR/$hook"
  fi
  echo "  Installed: $HOOKS_DIR/$hook"
done

# 3. Copy or download SKILL.md
# lena-activate.js resolves SKILL.md at __dirname/../skills/lena/SKILL.md
# When installed to ~/.claude/hooks/, that resolves to ~/.claude/skills/lena/SKILL.md
if [ -n "$REPO_ROOT" ] && [ -f "$REPO_ROOT/skills/lena/SKILL.md" ]; then
  cp "$REPO_ROOT/skills/lena/SKILL.md" "$SKILLS_DIR/SKILL.md"
else
  curl -fsSL "$REPO_RAW/skills/lena/SKILL.md" -o "$SKILLS_DIR/SKILL.md"
fi
echo "  Installed: $SKILLS_DIR/SKILL.md"

# 4. Wire hook into settings.json (idempotent)
if [ ! -f "$SETTINGS" ]; then
  echo '{}' > "$SETTINGS"
fi

# Back up existing settings.json before modifying
cp "$SETTINGS" "$SETTINGS.bak"

LENA_SETTINGS="$SETTINGS" LENA_HOOKS_DIR="$HOOKS_DIR" node -e "
  const fs = require('fs');
  const settingsPath = process.env.LENA_SETTINGS;
  const hooksDir = process.env.LENA_HOOKS_DIR;
  const hookScript = hooksDir + '/lena-activate.js';
  const settings = JSON.parse(fs.readFileSync(settingsPath, 'utf8'));
  if (!settings.hooks) settings.hooks = {};

  // SessionStart — auto-load LENA orchestration rules each session
  if (!settings.hooks.SessionStart) settings.hooks.SessionStart = [];
  const hasHook = settings.hooks.SessionStart.some(e =>
    e.hooks && e.hooks.some(h => h.command && h.command.includes('lena-activate.js'))
  );
  if (!hasHook) {
    settings.hooks.SessionStart.push({
      hooks: [{
        type: 'command',
        command: 'node \"' + hookScript + '\"',
        timeout: 10,
        statusMessage: 'Loading LENA...'
      }]
    });
  }

  fs.writeFileSync(settingsPath, JSON.stringify(settings, null, 2) + '\n');
  console.log('  Hooks wired in settings.json');
"

echo ""
echo "Done! Restart Claude Code to activate."
echo ""
echo "What's installed:"
echo "  - SessionStart hook: auto-loads LENA orchestration rules every session"
echo "  - Skill: ~/.claude/skills/lena/SKILL.md"
echo ""
echo "Usage:"
echo "  /lena                    Activate LENA orchestrator"
echo "  /lena build auth system  Immediate orchestrated task"
echo ""
