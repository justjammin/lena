# LENA hooks (Claude Code)

Bundled with the **lena** plugin. When the plugin is enabled, Claude Code runs these automatically. No manual `settings.json` merge for plugin installs.

## Standalone install

If you can't use `claude plugin install`, install hooks directly:

```bash
# From a repo clone
bash hooks/install.sh

# One-liner (no clone needed)
bash <(curl -s https://raw.githubusercontent.com/justjammin/lena/main/hooks/install.sh)

# Re-install / update over existing
bash hooks/install.sh --force
```

**What it installs:**
- `~/.claude/hooks/lena-activate.js` — SessionStart hook
- `~/.claude/hooks/package.json` — Node module config
- `~/.claude/skills/lena/SKILL.md` — orchestration rules

**Requires:** Node.js (`node` on PATH).

## `lena-activate.js` — SessionStart

- Runs at the start of each Claude Code session.
- Reads `skills/lena/SKILL.md`, strips YAML frontmatter, prints the body to stdout.
- That output is injected as **hidden** session context.
- Users stay primed as LENA until they say `stop lena`, `exit lena`, or `lena off`; the next session runs the hook again.

## Paths

| Install method | Hook path |
|----------------|-----------|
| `claude plugin install` | `${CLAUDE_PLUGIN_ROOT}/hooks/lena-activate.js` |
| `bash hooks/install.sh` | `~/.claude/hooks/lena-activate.js` |
| From repo (dev) | `node hooks/lena-activate.js` (run from repo root) |

In both installed modes, `lena-activate.js` resolves `SKILL.md` at `__dirname/../skills/lena/SKILL.md` — mapping correctly to the install location automatically.

## Disable

**Plugin install:** turn off or uninstall the **lena** plugin in Claude Code.

**Standalone install:** remove the SessionStart entry from `~/.claude/settings.json` and delete `~/.claude/hooks/lena-activate.js`.