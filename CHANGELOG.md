# Changelog

## [v1.5.0] — 2026-04-27

### What's new

**Back to Beads — and it's the right call**

v1.3.0 replaced Beads with Weave. That's now reversed. Beads is back as the execution tracking layer, properly wired into the orchestration loop this time: `bd create` before decomposition, `bd update --claim` before each agent dispatch, `bd close` after, `bd ready` to find what's unblocked next. The hard gate in Step 5 of the execution loop holds: no agent call until `bd list --status open` confirms every step is registered.

`bd prime` runs on SessionStart and PreCompact via Claude Code hooks, so LENA wakes up knowing what work is live even after compaction.

**SKILL.md went from 483 lines to 145**

The single monolithic skill file is now a navigation hub. Everything that isn't core routing logic lives in domain-specific subdirectories loaded on demand — progressive disclosure so the always-loaded context stays tight:

```
skills/lena/
  SKILL.md                        ← always loaded (~145 lines)
  routing/
    routing.md                    ← agent categories + subagent_type values
    task-classification.md        ← edge cases, scope expansion, Router pattern
  memory/
    ctx_knowledge.md              ← full ctx_knowledge API
    ctx_session.md                ← ctx_session API + when vs ctx_knowledge
    consolidation.md              ← end-of-session consolidation protocol
  orchestration/
    workflows.md                  ← 8 execution patterns + parallel dispatch rules
    agent-handoffs.md             ← 7-step execution loop with excellence gate
    beads.md                      ← Beads orchestration pattern + fallback
  query/
    graphify.md                   ← when + how LENA queries the graph
```

**Graphify for architecture and impact analysis**

Graphify is now the graph query layer. LENA uses it when `ctx_knowledge` doesn't have the answer: what calls what, how concepts connect, which nodes are hubs, what might break if X changes. The new `query/graphify.md` reference documents when to trigger a query, which mode to use (BFS/DFS/path/explain), and how to write durable findings back to `ctx_knowledge` tagged `[graph:HEAD]` so future sessions are free.

Graphify's MCP server (`--mcp`) means LENA can query the graph with tool calls when the server is configured, not just shell commands.

**Knowledge System Rules formalized**

Five explicit rules now live at the top of SKILL.md:

| System | Purpose | When |
|--------|---------|------|
| `ctx_knowledge` | Reusable facts, patterns, gotchas | Any project-specific insight |
| `ctx_session` | Decisions + findings this run | Track what happened this session |
| `bd` (Beads) | Workflow tracking, task state | Every orchestrated task |
| Graph tools | Relationships between entities | Architecture + impact analysis |
| `ctx_preload` | Pre-fetch only relevant context | Before each step |

**Never duplicate knowledge across systems. One source of truth per fact.**

**weave-planner removed**

The harness-native weave-planner agent is gone. Step 4B now belongs to LENA: write out the complete execution plan inline (title, category, agent, dependencies), verify every dep edge before `bd create` commands, no external agent needed.

### Files changed

| File | What changed |
|------|-------------|
| `skills/lena/SKILL.md` | Compressed 483 → 145 lines; Knowledge System Rules; Step 3B pointers to subdirs; Step 2 classification table |
| `skills/lena/routing/routing.md` | Agent categories table; removed Harness-Native Agents section (weave-planner gone) |
| `skills/lena/routing/task-classification.md` | Edge cases, scope expansion, Router pattern explanation |
| `skills/lena/memory/ctx_knowledge.md` | Full ctx_knowledge API: remember/recall/pattern/gotcha/consolidate |
| `skills/lena/memory/ctx_session.md` | Session API + when-to-use vs ctx_knowledge comparison |
| `skills/lena/memory/consolidation.md` | Consolidation protocol; graph findings added to Keep list |
| `skills/lena/orchestration/workflows.md` | 8 execution patterns; Step 4B rewritten — LENA does inline decomposition |
| `skills/lena/orchestration/agent-handoffs.md` | 7-step loop with Beads commands; Step 4B cross-ref updated |
| `skills/lena/orchestration/beads.md` | Full Beads pattern; output propagation; fallback |
| `skills/lena/query/graphify.md` | **New** — when + how LENA uses Graphify for graph queries |
| `hooks/lena-activate.js` | Removed weave-planner from BUILTIN_AGENTS + NAME_CAT |
| `install.js` | Guard agents/ dir existence; removed stale agentFiles log loop |
| `README.md` | Tool infrastructure: Weave → Beads, Wiki Memory → Graphify |

### Upgrading

Re-run `node install.js` or update the plugin. Run `bd setup claude` in any project that uses Beads to wire the SessionStart and PreCompact hooks. Run `/graphify <path>` in a project to build the graph before LENA will use it.

---

## [v1.4.0] — 2026-04-26

### What's new

**Agent pool — automatic, always fresh**

LENA now knows what agents are installed. At every session start, the hook scans `~/.claude/agents/`, `~/.cursor/agents/`, and the workspace equivalents, categorizes each agent into one of 14 routing categories, and injects a compact `## Available Agents` block into the session context. New or custom agents show up automatically — no manual SKILL.md editing required.

The scan is mtime-based: it only re-runs when an agent file is newer than the cache, with a 14-day hard ceiling as a safety net. Cache lives at `~/.claude/.lena-agent-pool.json`. Custom agents not in the built-in list are flagged with `*` so LENA knows they're non-standard but valid dispatch targets.

14 categories: Architecture, Implementation, Debugging, Code Review, Performance, Testing, Database, DevOps, Documentation, ML/AI, Mobile, Content/Writing, Research/Analysis, Enterprise/Domain, Orchestration.

**Repo context at session start — zero MCP cost**

The hook now injects lightweight git context on every session: last 3 commits, current branch and HEAD, working tree stat. Pure shell, ~5ms, no MCP round-trip.

For deeper structural analysis, LENA follows a two-step amortized pattern: run `ctx_architecture` + `ctx_graph` once, write `@node[repo:analysis:overview]` to the wiki keyed by git HEAD. Every subsequent session sees the node and skips the analysis entirely. Re-runs only when HEAD changes.

**`repo_analysis` operation in wiki-scribe**

Wiki-scribe has a new operation. LENA runs the MCP tools (only LENA has MCP access), then dispatches wiki-scribe as a background agent with the raw output. Wiki-scribe owns the DSL write, `relations.md` edge, `index.md` entry, and `log.md` append. Freshness check first — if `+head:` matches current HEAD, skip with "fresh — skip". Lineage pointer set on update.

**LENA Step 0 extended**

After loading wiki context, LENA now checks for a `repo:analysis:` node. If absent or stale (HEAD mismatch), it runs `ctx_architecture` + `ctx_graph` inline and dispatches wiki-scribe to persist the result in the background before the first orchestrated step.

### Files changed

| File | What changed |
|------|-------------|
| `hooks/lena-activate.js` | Agent pool scan (mtime-cached, 14 categories, `*`-flagged custom agents). Lightweight git repo context. Wiki `repo:analysis:` check with LENA instruction when absent. |
| `skills/lena/SKILL.md` | Step 0: repo analysis check — detect missing/stale node, run MCP tools inline, dispatch wiki-scribe as background write packet. |
| `skills/wiki-scribe/SKILL.md` | New `repo_analysis` operation: receives LENA packet, freshness check, writes typed Concept node with `+head:`, updates `relations.md` + index + log. |
| `agents/wiki-scribe.md` | Same `repo_analysis` operation added to agent definition. |

### Upgrading

Re-run `node install.js` or update the plugin. New sessions pick up the agent pool and repo context automatically. First session on a repo with no wiki triggers the one-time `ctx_architecture` + `ctx_graph` run; subsequent sessions are free.

---

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
