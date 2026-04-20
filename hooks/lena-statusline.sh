#!/bin/bash
# lena — statusline badge script for Claude Code
# Shows [LENA] or [LENA:ROLE] in blue, reflecting which hat LENA is currently wearing.
#
# Usage in ~/.claude/settings.json:
#   "statusLine": { "type": "command", "command": "bash /path/to/lena-statusline.sh" }
#
# Installed automatically by install.js.

LENA_ACTIVE="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/.lena-active"
LENA_HAT="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/.lena-hat"

# Refuse symlinks — prevents terminal-escape injection via flag file contents.
[ -L "$LENA_ACTIVE" ] && exit 0
[ ! -f "$LENA_ACTIVE" ] && exit 0

HAT=""
if [ -f "$LENA_HAT" ] && [ ! -L "$LENA_HAT" ]; then
  HAT=$(head -c 64 "$LENA_HAT" 2>/dev/null | tr -d '\n\r' | tr '[:upper:]' '[:lower:]')
  HAT=$(printf '%s' "$HAT" | tr -cd 'a-z0-9-')
fi

if [ -z "$HAT" ] || [ "$HAT" = "lena" ]; then
  printf '\033[38;5;39m[LENA]\033[0m'
else
  SUFFIX=$(printf '%s' "$HAT" | tr '[:lower:]' '[:upper:]')
  printf '\033[38;5;39m[LENA:%s]\033[0m' "$SUFFIX"
fi
