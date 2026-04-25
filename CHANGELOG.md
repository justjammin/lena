# Changelog

## [v1.3.0] — 2026-04-24

### What's new

**Weave and Wiki Memory replace Beads and Graphify**

Beads and Graphify got the job done, but they had a ceiling. Weave and Wiki Memory are the replacements — built for the same jobs but designed to compound across sessions and pass real context between steps, not just task state.

**Weave** takes over execution tracking. Steps still get titles, roles, priorities, and dependency edges, but Weave adds something Beads didn't have: output propagation. `wv ready` claims the next task and injects any upstream output blobs directly into its input field. `wv done --output` closes it and passes the result downstream. Downstream steps get the actual result — no guessing, no re-explaining.

`wv init` anchors `.weave/` at the git root, not the cwd. That matters for monorepos and deeply nested project structures.

**Wiki Memory** takes over long-term memory. Where Graphify stored flat JSON nodes, Wiki Memory uses a content-addressed file graph in `wiki/` with a structured node DSL. Each node has a sha6 content hash and an optional `~parent` pointer that chains versions into a lineage. Same content → same hash → write skipped. The graph doesn't grow with duplicates.

At session start, LENA reads the last few log entries and loads relevant prior nodes. At session end, a summary node goes in. Future sessions aren't starting cold.

**Harness-native agents**

Two specialist agents now ship with LENA and install to `~/.claude/agents/`:

- **wiki-scribe** — owns the Wiki Memory layer. Knows the node DSL, sha6 hashing, lineage pointers, and staleness detection against repo files. Invoke at session start to load prior context, on significant decisions to persist knowledge, and at session end to version skills and append the session log.
- **weave-planner** — decomposes complex multi-step goals into `wv` execution graphs. Selects the execution pattern (Pipeline, Parallel, Feedback Loop, etc.), maps steps to agent roles, wires `--depends` edges, and outputs a ready-to-run `wv create` command block. No prose decomposition without the commands.

### Files changed

| File | What changed |
|------|-------------|
| `skills/lena/SKILL.md` | Tool Infrastructure: Beads → Weave, Graphify → Wiki Memory. Sub-agent execution patterns. Excellence gate and delivery notification. |
| `skills/weave/SKILL.md` | New — Weave skill with full LLM-agnostic contract and `wv` command reference |
| `agents/wiki-scribe.md` | New — harness-native agent for Wiki Memory layer |
| `agents/weave-planner.md` | New — harness-native agent for Weave graph decomposition |
| `bin/wv` | New — Weave CLI, single Node.js executable, zero external deps |
| `install.js` | Copies `wv` to `~/.local/bin`, agents to `~/.claude/agents/` |
| `README.md` | Tool infrastructure section rewritten: Weave and Wiki Memory |

### Upgrading

Re-run `node install.js` or update the plugin. The hook layer is unchanged — new features are inside the skill and the new files.

---

## [v1.2.0] — 2026-04-24

### What's new

**LENA got a crew**

Solo was fine. Crew is better.

LENA now has four infrastructure tools she can pull in on any orchestrated job. They're not agents — they're the support layer that keeps an operation running while specialists do the actual work.

**Beads** handles task tracking. When a job splits into steps, Beads logs each one with a title, role, status, and dependencies. LENA updates them as she goes. If Beads isn't around, she falls back to a numbered checklist in the response — nothing stops.

One wrinkle: if Beads is installed but the project hasn't been initialized yet, LENA now knows to run `bd init` before trying anything. She checks `bd ready` first. If that fails, she initializes. If *that* fails, checklist mode. No drama.

**Graphify** is long-term memory. At the start of a session, LENA checks it for prior context on what she's about to work on. Mid-task, she writes key decisions to it. At the end, she writes a summary node so future-LENA isn't starting cold. If Graphify isn't available, she asks one targeted question instead and keeps a scratchpad in the response.

**Lean CTX** keeps the context window from turning into a disaster zone. Before each sub-agent call, LENA compresses the current context and injects a tidy `## Context` block into the prompt — no raw conversation dumps. If it's not there, she writes the summary herself and caps it at 500 tokens.

**Caveman** compresses LENA's own output. Six levels: `lite`, `full`, `ultra`, and three `wenyan-*` variants for classical Chinese compression. LENA adopts whichever level is already active — she doesn't touch the setting if the caveman skill already set it. That's the **no-override rule**: if caveman mode was set before LENA showed up, she inherits it and keeps her hands off.

**Concurrent steps**

LENA can now run independent sub-agent steps at the same time. Testing and Documentation after an Implementation pass? Both go out concurrently. Hat writes are skipped during concurrent steps to avoid file corruption — they resume on the next sequential step.

**Hat reset**

After every direct-execution answer, LENA resets the hat back to `main`. The statusline doesn't hold a role badge between tasks anymore.

### Files changed

| File | What changed |
|------|-------------|
| `skills/lena/SKILL.md` | Tool Infrastructure section: Beads, Graphify, Lean CTX, Caveman — each with usage pattern, fallback, and init/no-override rules |
| `README.md` | Tool infrastructure section added and rewritten |

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

Here's the thing — when LENA handled tasks solo, she was generically herself. Now she picks a role. Debug session? She's a `debugger`. Code quality check? `code-reviewer`. Writing server logic? `backend-developer`. Same routing logic under the hood, but she thinks like the right specialist instead of a generalist doing an impression.

**Statusline badge**

There's a blue `[LENA]` badge in the Claude Code statusline whenever LENA's active. When she's mid-task and using tools, the badge updates live: `[LENA:DEBUGGER]`, `[LENA:BACKEND-DEVELOPER]`, and so on. Every new session resets it to `[LENA]`.

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

Re-run `node install.js` or update the plugin. New sessions pick everything up automatically.

---

## [v1.0.0] — Initial release

LENA shipped. AI orchestrator for Claude Code — routes single-step tasks directly, decomposes multi-step work and delegates to specialist agents.
