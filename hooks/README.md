# LENA hooks (Claude Code)

Bundled with the **lena** plugin. When the plugin is enabled, Claude Code runs these automatically. No manual `settings.json` merge for plugin installs.

## `lena-activate.js` — SessionStart

- Runs at the start of each Claude Code session.
- Reads `skills/lena/SKILL.md`, strips YAML frontmatter, prints the body to stdout.
- That output is injected as **hidden** session context (same pattern as the caveman plugin).
- Users stay primed as LENA until they say `stop lena`, `exit lena`, or `lena off`; the next session runs the hook again.

## Paths

- Installed plugin: `${CLAUDE_PLUGIN_ROOT}/hooks/lena-activate.js` (see `.claude-plugin/plugin.json`).
- From this repo: `node hooks/lena-activate.js` (run from repository root).

## Disable

Turn off or uninstall the **lena** plugin in Claude Code; hooks are defined in the plugin manifest, not in your global `settings.json`.
