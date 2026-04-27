# LENA: AI Orchestrator

Okay so this is the thing I've been building. You know that moment when you ask your AI for something small and it suddenly wants to spin up a committee? Or you throw something big at it and one tired generalist tries to carry the whole thing? Yeah. That's what LENA is built to fix.

**L.E.N.A.** — Logical Execution & Navigation Assistant. She's a Claude Code skill that thinks like a principal engineer: picky about *how* work gets done, not just whether it gets done. Quick task? She handles it and gets out of the way. Actually a project in disguise? She breaks it apart and hands each piece to whoever's actually built for it.

---

## What actually happens

Every request hits a gate:

```
Single task + one domain + clear requirements
  → Direct execution (no agents, no ceremony)

Multiple steps OR multiple domains OR fuzzy requirements OR "build / refactor / fix the whole thing"
  → Orchestrated mode (split → route → stitch)
```

### Direct work

Simple paths don't need a parade. LENA handles them solo: fix the bug, write the helper, explain the file, generate tests. Fast, quiet, done.

**Examples:** patch a known issue, draft a function, walk through code, generate tests.

### When LENA brings in backup

Bigger work gets decomposed deliberately — not dumped on one agent. Each chunk goes to whoever's actually built for it. Context passes forward so nobody's starting from scratch mid-chain.

Steps with hard dependencies run in order. Steps without — testing + documentation after implementation, security + code review on the same artifact — run concurrently.

---

## Who LENA can call

She groups work into categories, picks the right agents, and only pulls in the lanes the task actually needs. The runtime may not expose every type; LENA maps to what's available.

| Category | What it's for | Agents (typical) |
|----------|---------------|-------------------|
| **Architecture** | System design, tradeoffs | `architect-reviewer` |
| **Implementation** | Writing and changing code | `backend-developer`, `frontend-developer`, `fullstack-developer`, `refactoring-specialist` |
| **Debugging** | Root cause analysis | `debugger`, `error-detective` |
| **Code Review** | Quality and correctness | `code-reviewer` |
| **Performance** | Optimization (incl. dev workflow / build loop) | `dx-optimizer` + database agents when the problem is queries |
| **Testing** | Test generation | `test-automator` |
| **Security** | Vulnerabilities, hardening, best practices | `code-reviewer` with an explicit security brief |
| **Database** | Schema, queries, data layer | `database-administrator`, `database-optimizer`, `postgres-pro` |
| **DevOps** | Deployment, infrastructure | `cloud-architect`, `kubernetes-specialist` |
| **Documentation** | Explanations and docs | `documentation-engineer`, `technical-writer` |
| **ML / AI** (when relevant) | LLM systems, RAG, tuning | `llm-architect` |

---

## Adding custom agents for LENA to choose from

LENA works great with VoltAgents subagents — honestly worth pairing them.

Repo: [VoltAgent SubAgent Collection](https://github.com/VoltAgent/awesome-claude-code-subagents).

### Cursor (`subagent_type` + `.cursor/agents`)

**Where files live**

| Scope | Path | Notes |
|-------|------|--------|
| **Project** | `.cursor/agents/*.md` | Current repo only; wins over user scope on name collision |
| **User** | `~/.cursor/agents/*.md` | Available in every project |

`subagent_type` goes in the **Tool / Agent call**, not the file. The string must match an agent Cursor actually registered.

```markdown
---
name: my-api-hardening
description: Use for auth, input validation, and OWASP-style API reviews.
model: inherit
readonly: false
---

Your system prompt for this specialist goes here.
```

The `description` is what the parent reads to decide whether to hand work off. Get that right.

Docs: [Subagents (Cursor)](https://cursor.com/docs/agent/subagents).

### Claude Code (`.claude/agents`)

**Where files live** (higher priority wins on name collision)

| Scope | Path | Notes |
|-------|------|--------|
| **Managed / org** | Per your admin | Highest precedence |
| **CLI (session only)** | `claude --agents '{ ... }'` | JSON map; same fields as frontmatter; not saved to disk |
| **Project** | `.claude/agents/*.md` | Walks up from cwd; good to commit for the team |
| **User** | `~/.claude/agents/*.md` | Personal agents in every project |
| **Plugin** | Plugin's `agents/` | Lowest precedence; ships with plugins like LENA |

`--add-dir` adds file access only — those extra roots are **not** scanned for agents.

**Minimum frontmatter** (`name` and `description` required; body = system prompt)

```markdown
---
name: my-api-hardening
description: Use for auth, input validation, and OWASP-style API reviews.
tools: Read, Glob, Grep
---

Your system prompt for this specialist goes here.
```

Optional keys: `tools`, `disallowedTools`, `model`, `permissionMode`, `skills`, `mcpServers`, `hooks`, `maxTurns`. Plugin-defined agents ignore `hooks`, `mcpServers`, and `permissionMode` — copy the file into `.claude/agents/` or `~/.claude/agents/` if you need those.

**After editing:** restart the session or run `/agents` to reload.

Docs: [Subagents (Claude Code)](https://docs.claude.com/en/docs/claude-code/subagents).

---

## Tool infrastructure

Here's where it gets fun. LENA runs on four tools underneath — execution tracking, architecture graph queries, context management, and output compression. Each one has a fallback if it's not installed, so nothing breaks.

### Beads — Execution tracking

Download [Beads](https://github.com/gastownhall/beads)

Beads is one of my favorites in this stack. It's a Dolt-backed graph issue tracker — task state that actually survives context compaction. When LENA splits a job into steps, every step gets a ticket before anything runs. Title, role, priority, dependency edges — all locked in upfront.

```bash
bd init --quiet --stealth  # initialize at git root
bd create "..." -t task    # register a task
bd ready                   # claim next unblocked task
bd update <id> --claim     # mark in-progress
bd close <id>              # mark complete
bd dep tree <id>           # show dependency graph
```

The thing I love about this: the hard rule is that no agent gets dispatched until every step is registered. LENA uses `bd ready` to find what's actually unblocked at each point, and `bd list --status open` to make sure nothing got silently dropped before wrapping up.

`bd prime` runs on SessionStart and PreCompact via Claude hooks — LENA always wakes up knowing what's live.

**Fallback:** numbered checklist inline. Outputs noted as code blocks after each step.

---

### Graphify — Architecture graph

Download [Graphify](https://github.com/safishamsi/graphify)

Okay this one is genuinely impressive. Graphify takes any folder of files — code, docs, papers, notes, whatever you've got — and builds a persistent knowledge graph from it. Community detection, a real audit trail, queryable relationships.

LENA uses it when she needs to understand architecture or trace impact: what calls what, how concepts connect, which nodes are the real hubs. The graph lives across sessions. A query takes seconds instead of re-reading the whole codebase from scratch.

```bash
graphify <path>                        # build the graph
graphify query "<question>"            # BFS traversal — broad context
graphify query "<question>" --dfs      # DFS — trace a specific path
graphify path "AuthModule" "Database"  # shortest path between two concepts
graphify explain "NodeName"            # plain-language neighborhood
```

Every edge gets tagged EXTRACTED, INFERRED, or AMBIGUOUS — so you know what was found versus what was guessed. It also exposes an MCP server (`--mcp`) so LENA can query the graph via tool calls when the server's configured. Key findings flow back into cross-session memory tagged `[graph:HEAD]`, so the next session doesn't have to re-query things we already know.

**Fallback:** semantic search for meaning-based lookup when no graph exists.

---

### Lean CTX — Context management

Download [Lean CTX](https://github.com/yvgude/lean-ctx)

Lean CTX keeps the context window from turning into a disaster zone. Before each sub-agent call, it compresses active context and injects a clean `## Context` block into the prompt — no raw conversation dumps, just the relevant state. It also handles `ctx_knowledge` and `ctx_session`: cross-session memory for project facts, architectural decisions, and session findings that survive compaction and carry forward automatically.

**Fallback:** manual context summary (task goal, decisions so far, current step, blockers) injected into each sub-agent prompt. Cap at 500 tokens per call.

---

### Caveman — Output compression

Download [Caveman](https://github.com/JuliusBrussee/caveman)

Caveman compresses LENA's output. Six levels — pick the intensity. LENA inherits whatever's already active and never overrides it.

| Level | Behavior |
|-------|----------|
| `lite` | No filler or hedging. Articles and full sentences kept. Tight but readable |
| `full` | Drop articles, fragments OK, short synonyms. Classic caveman |
| `ultra` | Abbreviate (DB / auth / config / req / res / fn / impl), arrows for causality (X → Y), one word when one word works |
| `wenyan-lite` | Semi-classical Chinese. Drop filler, keep grammar structure |
| `wenyan-full` | Maximum classical terseness. 80–90% character reduction |
| `wenyan-ultra` | Extreme abbreviation with classical Chinese feel |

Not compressed: code blocks, error messages, security warnings, destructive action confirmations, multi-step sequences where order matters.

**Fallback:** terse prose — drop filler, hedging, and pleasantries.

---

### Tool availability check

LENA checks what's actually installed at the start of any orchestrated run:

| Tool | Available | Unavailable |
|------|-----------|-------------|
| Beads (`bd`) | Full execution graph, dependency tracking | Inline numbered checklist |
| Graphify | Graph queries, architecture + impact analysis | Semantic search fallback |
| Lean CTX | Compress per sub-agent call; cross-session memory | Manual 500-token context block |
| Caveman | Compress all human-facing output | Terse prose manually |

---

## Install

### Claude Code (recommended)

```bash
claude plugin add justjammin/lena
```

This registers a SessionStart hook that loads the LENA skill into hidden context on every new session. Routing rules kick in from the first message until you say `stop lena`, `exit lena`, or `lena off`. `/lena` still works as an explicit trigger.

### npx

```bash
npx lena-ai
```

### Manual

```bash
mkdir -p ~/.claude/skills/lena
curl -o ~/.claude/skills/lena/SKILL.md \
  https://raw.githubusercontent.com/justjammin/lena/main/skills/lena/SKILL.md
```

Manual install is skill only — no SessionStart hook. Use `/lena` each thread.

---

## Usage

**Plugin:** LENA is already primed when the session opens. `/lena` is optional.

**Skill-only:** type `/lena`:

```
/lena
```

First `/lena` in a thread: **LENA active. What are we building?** After that, LENA routes every message until `stop lena`, `exit lena`, or `lena off`. With the plugin, the next session primes LENA again automatically via the hook.

### Two quick examples

**Small and clear** (LENA won't over-orchestrate):

```
/lena
> Fix the N+1 query in the user dashboard

→ LENA handles it directly
```

**Big and messy** (LENA lines up the right people):

```
/lena
> Build a complete JWT auth system with refresh tokens, tests, and documentation

→ Rough flow:
  1. architect-reviewer ... system shape and contracts
  2. backend-developer ... auth + refresh tokens
  3. test-automator ... tests
  4. documentation-engineer ... API docs
```

---

## Rules LENA lives by

1. **Correct beats clever.** Always.
2. **If it's vague, LENA asks once.** One sharp question. Not twenty.
3. **No scope creep from LENA's side.** Build what was asked.
4. **No half-finished proof of concept when you needed something real.**
5. **LENA explains when it helps.** Not because the template said to.

---

## Where it runs

| Environment | Install |
|-------------|---------|
| Claude Code | `claude plugin add justjammin/lena && claude plugin install lena@lena` |
| **Codex** | Clone repo → `/plugins` → Search "lena" → Install |
| **Gemini CLI** | `gemini extensions install https://github.com/justjammin/lena` |
| **Cursor** | `npx skills add justjammin/lena -a cursor` |
| **Windsurf** | `npx skills add justjammin/lena -a windsurf` |
| **Copilot** | `npx skills add justjammin/lena -a github-copilot` |
| **Cline** | `npx skills add justjammin/lena -a cline` |
| **Any other** | `npx skills add justjammin/lena` |

---


<summary><strong>Any other agent (opencode, Roo, Amp, Goose, Kiro, and 40+ more)</strong></summary>

[npx skills](https://github.com/vercel-labs/skills) supports 40+ agents:

```bash
npx skills add justjammin/lena           # auto-detect agent
npx skills add justjammin/lena -a amp
npx skills add justjammin/lena -a augment
npx skills add justjammin/lena -a goose
npx skills add justjammin/lena -a kiro-cli
npx skills add justjammin/lena -a roo
# ... and many more
```

## License

MIT. [justjammin](https://github.com/justjammin).
