# LENA: AI Orchestrator

You know that moment when you ask your AI for something small and it suddenly wants a committee? Or you ask for something huge and one tired generalist tries to do it all? That's the friction this skill is built to fix.

**L.E.N.A.** stands for Logical Execution & Navigation Assistant. LENA is a Claude Code skill that acts like a principal engineer who's picky about *how* work gets done. Before touching your task, LENA sorts it: quick solo work stays quick. Anything that's really a project gets broken up and handed to specialists who fit the job.

---

## What actually happens

LENA runs a gate before every request:

```
Single task + one domain + clear requirements
  → Direct execution (no agents, no ceremony)

Multiple steps OR multiple domains OR fuzzy requirements OR "build / refactor / fix the whole thing"
  → Orchestrated mode (split → route → stitch)
```

### Direct work

Straight paths don't need a parade. LENA handles them alone: fix the bug, write the helper, explain the file, generate tests. Fast, quiet, done.

**Examples:** patch a known issue, draft a function, walk through code, generate tests.

### When LENA brings in backup

Bigger work gets decomposed deliberately. Each chunk goes to whoever's built for it. Context passes forward so you're not re-explaining yourself three times.

Steps with hard dependencies run in order. Steps with no inter-dependencies — testing + documentation after implementation, or security + code review on the same artifact — run concurrently when possible.

---

## Who LENA can call

LENA groups work into categories, then picks agents that fit. Most tasks only need a couple of lanes, not the whole roster. The runtime may not expose every agent type; LENA maps to what's available.

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

LENA works well with VoltAgents subagents — worth pairing the two.

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

LENA ships with four infrastructure layers: execution tracking, long-term memory, context management, and output compression. Each has a fallback — if a tool isn't available, LENA keeps going.

### Weave — Execution graph

Weave is LENA's task tracking and execution layer. When a job splits into steps, each step gets registered in `.weave/` — a git-root-anchored JSON store — with a title, assigned agent role, priority, and dependency edges.

The `wv` CLI manages the lifecycle:

```bash
wv init          # initialize at git root
wv create "..."  # register a task
wv ready         # claim next task; injects upstream outputs into input field
wv done --output # close task; passes result downstream
wv graph         # show dependency DAG
wv stats         # task count by status
```

The output propagation is the real feature. When Step 3 runs, it doesn't have to guess what Step 2 produced — `wv ready` injects the actual output blob. Context flows through the graph automatically.

**Fallback:** numbered checklist in the response, updated as steps complete.

---

### Wiki Memory — Long-term memory

Wiki Memory is a content-addressed file graph stored in `wiki/` at the project root. Nodes are written in a structured DSL:

```
@node[domain:subdomain:topic] ^{sha6} ~{parent_sha6}
+task:    what was being solved
+outcome: what was produced or decided
+agents:  [role, role]
+method:  manual|agent-generated
+t:       ISO8601
>link:    related:node:address
```

Each node has a sha6 content hash and an optional `~parent` pointer for lineage. Same content → same hash → write skipped. The graph stays clean without manual dedup.

At session start, LENA reads the last few log entries and loads relevant prior nodes. Mid-task, it writes decisions and outcomes. At session end, a summary node goes in so future sessions aren't starting cold.

**Fallback:** one question at session start for prior context; `## Session Memory` block for in-session decisions; 3–5 bullet summary at end offered for manual save.

---

### Lean CTX — Context management

Lean CTX compresses active context before each sub-agent call and injects a `## Context` block into the prompt. No raw conversation dumps — just the relevant state. Runs on every orchestrated step and when context window pressure rises.

**Fallback:** manual context summary (task goal, decisions so far, current step, blockers) injected into each sub-agent prompt. Cap at 500 tokens per call.

---

### Caveman — Output compression

Caveman compresses LENA's own output at a configurable intensity level. LENA inherits whatever level is active — she doesn't override it if you've already set it.

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

At the start of any orchestrated execution, LENA checks what's available:

| Tool | Available | Unavailable |
|------|-----------|-------------|
| Weave (`wv`) | Full execution graph, output propagation | Inline checklist |
| Wiki Memory | Background batch writes, read-only session-start load | Session scratchpad + end summary |
| Lean CTX | Compress per sub-agent call | Manual 500-token context block |
| Caveman | Compress all human-facing output | Terse prose manually |

---

## Install

### Claude Code (recommended)

```bash
claude plugin add justjammin/lena
```

The plugin registers a SessionStart hook that loads the LENA skill into hidden context on every new session. Routing rules apply from the first message until you say `stop lena`, `exit lena`, or `lena off`. `/lena` still works as an explicit trigger.

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
