# Changelog

## [v1.2.0] — 2026-04-24

### What's new

**LENA got a crew**

Solo was fine. Crew is better.

LENA now has four infrastructure tools she can pull in on any orchestrated job. They're not agents — they're more like the support staff that keeps an operation running while the specialists do the actual work.

**Beads** handles task tracking. When a job splits into steps, Beads logs each one with a title, role, status, and dependencies. LENA updates them as she goes. If Beads isn't around, she falls back to a numbered checklist in the response — nothing stops.

One wrinkle: if Beads is installed but the project hasn't been initialized yet, LENA now knows to run `bd init` before trying anything. She checks `bd ready` first. If that fails, she initializes. If *that* fails, checklist mode. No drama.

**Graphify** is long-term memory. At the start of a session, LENA checks it for prior context on what she's about to work on. Mid-task, she writes key decisions to it. At the end, she writes a summary node so future-LENA isn't starting cold. If Graphify isn't available, she asks one targeted question instead and keeps a scratchpad in the response.

**Lean CTX** keeps the context window from turning into a disaster zone. Before each sub-agent call, LENA compresses the current context and injects a tidy `## Context` block into the prompt — no raw conversation dumps. If it's not there, she writes the summary herself and caps it at 500 tokens.

**Caveman** compresses LENA's own output. Six levels: `lite`, `full`, `ultra`, and three `wenyan-*` variants for classical Chinese compression. LENA adopts whichever level is already active — she doesn't touch the setting if the caveman skill already set it. That's the **no-override rule**: if caveman mode was set before LENA showed up, she inherits it and keeps her hands off.

**Concurrent steps**

LENA can now run independent sub-agent steps at the same time. Testing and Documentation after an Implementation pass? Both go out concurrently. She states when she's doing this. Hat writes are skipped during concurrent steps to avoid file corruption — they resume on the next sequential step.

**Hat reset**

After every direct-execution answer, LENA resets the hat back to `main`. The statusline doesn't hold a role badge between tasks anymore.

### Files changed

| File | What changed |
|------|-------------|
| `skills/lena/SKILL.md` | Tool Infrastructure section: Beads, Graphify, Lean CTX, Caveman — each with usage pattern, fallback, and init/no-override rules |
| `README.md` | Tool infrastructure section added and rewritten in plain documentarian voice |

### Upgrading

Re-run `node install.js` or update the plugin. Nothing structural changed in the hook layer — new features are all inside the skill.

---

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