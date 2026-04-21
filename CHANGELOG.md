# Changelog

## [v1.1.2] — 2026-04-21

### What's new

**LENA learned how to take off her hat**

## [v1.1.1] — 2026-04-20

### What's new

**LENA's hat now shows in the right spot**

## [v1.1.0] — 2026-04-20

### What's new

**LENA wears a hat**

Here's the thing — when LENA handled tasks solo, she was kind of generically herself. Now she picks a role. Debug session? She's a `debugger`. Code quality check? `code-reviewer`. Writing server logic? `backend-developer`. Same routing logic under the hood, but she actually thinks like the right specialist instead of a generalist doing an impression of one.

**Statusline badge**

You'll notice a blue `[LENA]` badge in the Claude Code statusline whenever LENA's active. Worth noting: when she's mid-task and using tools, the badge updates live to show which hat she's wearing — `[LENA:DEBUGGER]`, `[LENA:BACKEND-DEVELOPER]`, etc. Every new session resets it back to `[LENA]`.

**Smarter install**

`install.js` used to punt if you already had a `statusLine` configured. Now it chains LENA's badge onto whatever you've got — no manual config edits. Nothing set up yet? It handles that too.

### Files changed

| File | What changed |
|------|-------------|
| `skills/lena/SKILL.md` | Step 2A: role adoption + hat-writing instruction |
| `hooks/lena-activate.js` | Writes `.lena-active` flag and resets `.lena-hat` each session |
| `hooks/lena-statusline.sh` | **New** — blue statusline badge script |
| `install.js` | Copies statusline script, auto-sets or chains `statusLine` in `settings.json` |

### Upgrading

Re-run `node install.js` or update the plugin in Claude Code. New sessions pick everything up automatically.

---

## [v1.0.0] — Initial release

LENA shipped. AI orchestrator for Claude Code — routes single-step tasks directly, decomposes multi-step work and delegates to specialist agents.