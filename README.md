# LENA: AI Orchestrator

You know that moment when you ask your AI for something small and it suddenly wants a committee? Or you ask for something huge and one tired generalist tries to do it all? That's the friction this skill is for.

**L.E.N.A.** stands for Logical Execution & Navigation Assistant. LENA is a Claude Code skill that behaves more like a principal engineer who's picky about *how* work gets done. Before LENA touches your task, LENA sorts it: quick solo work stays quick. Anything that's really a project gets broken up and handed to specialists who actually fit the job.

You spend less energy babysitting the process. You still get answers you can trust.

---

## What actually happens

LENA runs a simple gate before every request:

```
Single task + one domain + clear requirements
  → Direct execution (no agents, no ceremony)

Multiple steps OR multiple domains OR fuzzy requirements OR "build / refactor / fix the whole thing"
  → Orchestrated mode (split the work → route it → stitch it back together)
```

### When it's just direct work

Straight paths don't need a parade. LENA handles them alone: fix the bug, write the helper, explain the file, sketch the test. Fast, quiet, done.

**Examples:** patch a known issue, draft a function, walk through code, generate tests.

### When LENA brings in backup

Bigger work gets decomposed on purpose. Each chunk goes to whoever's built for that kind of problem. Context gets passed along so you're not re-explaining yourself three times.

**Examples:** auth end-to-end, a real refactor, chasing a production failure across layers.

---

## Who LENA can call

LENA groups work into **categories** (architecture, implementation, debugging, and so on), then picks agents that fit. Most tasks only need a couple of lanes ... not the whole roster. The runtime may not expose every agent type; LENA maps to what's actually available.

| Category | What it's for | Agents (typical) |
|----------|---------------|-------------------|
| **Architecture** | System design, tradeoffs | `architect-reviewer` |
| **Implementation** | Writing and changing code | `backend-developer`, `frontend-developer`, `fullstack-developer`, `refactoring-specialist` |
| **Debugging** | Root cause analysis | `debugger`, `error-detective` |
| **Code Review** | Quality and correctness | `code-reviewer` |
| **Performance** | Optimization (incl. dev workflow / build loop) | `dx-optimizer` ... plus database agents when the problem is queries or schema |
| **Testing** | Test generation | `test-automator` |
| **Security** | Vulnerabilities, hardening, best practices | `code-reviewer` with an explicit security brief |
| **Database** | Schema, queries, data layer | `database-administrator`, `database-optimizer`, `postgres-pro` |
| **DevOps** | Deployment, infrastructure | `cloud-architect`, `kubernetes-specialist` |
| **Documentation** | Explanations and docs | `documentation-engineer`, `technical-writer` |
| **ML / AI** (when relevant) | LLM systems, RAG, tuning | `llm-architect` |

---

## Adding custom agents for LENA to choose from

LENA works well with VoltAgents subagents and I highly recommend pairing the two tools together. 

Repo: [VoltAgent SubAgent Collection](https://github.com/VoltAgent/awesome-claude-code-subagents).

### Cursor (`subagent_type` + `.cursor/agents`)

**Where files live**

| Scope | Path | Notes |
|-------|------|--------|
| **Project** | `.cursor/agents/*.md` | Current repo only; wins if the same `name` exists in user scope |
| **User** | `~/.cursor/agents/*.md` | Available in every project |

You don't put `subagent_type` in the file. That's the **Task / Agent tool argument** when something delegates. The string must match an agent Cursor actually registered.

```markdown
---
name: my-api-hardening
description: Use for auth, input validation, and OWASP-style API reviews.
model: inherit
readonly: false
---

Your system prompt for this specialist goes here.
```

Nail the `description` ... that's how the parent decides to hand work off. Other keys (`model`, `readonly`, `is_background`, etc.) are in Cursor's docs.

Docs: [Subagents (Cursor)](https://cursor.com/docs/agent/subagents).

### Claude Code (`.claude/agents`)

**Where files live** (higher priority wins when the same `name` collides)

| Scope | Path | Notes |
|-------|------|--------|
| **Managed / org** | Per your admin | Highest precedence if your org uses managed agents |
| **CLI (session only)** | `claude --agents '{ ... }'` | JSON map of agents; same fields as file frontmatter; not saved to disk |
| **Project** | `.claude/agents/*.md` | Walks up from the cwd; good to commit for the team |
| **User** | `~/.claude/agents/*.md` | Personal agents in every project |
| **Plugin** | Plugin's `agents/` | Lowest precedence; ships with plugins like LENA |

`--add-dir` adds file access only ... those extra roots are **not** scanned for agents.

**Minimum frontmatter** (`name` and `description` are required in Claude Code; body = system prompt)

```markdown
---
name: my-api-hardening
description: Use for auth, input validation, and OWASP-style API reviews.
tools: Read, Glob, Grep
---

Your system prompt for this specialist goes here.
```

Common optional keys include `tools`, `disallowedTools`, `model`, `permissionMode`, `skills` (preload skill content into that agent), `mcpServers`, `hooks`, `maxTurns`, and more ... see docs. **Plugin-defined agents** ignore some sensitive keys (`hooks`, `mcpServers`, `permissionMode`) for security; copy the file into `.claude/agents/` or `~/.claude/agents/` if you need those.

**After you add or edit a file:** restart the session or run **`/agents`** so Claude Code reloads the list.

Docs: [Subagents (Claude Code)](https://docs.claude.com/en/docs/claude-code/subagents).

---

## Install

### Claude Code (recommended)

```bash
claude plugin add justjammin/lena
```

With the **plugin**, Claude Code runs a **SessionStart** hook that loads the LENA skill into hidden context on **every new session**, so routing rules apply from the first message until you say **`stop lena`**, **`exit lena`**, or **`lena off`**. You can still type **`/lena`** for the explicit **LENA active** line.

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

Manual install is **skill only** (no SessionStart hook). Use **`/lena`** each thread if you want LENA behavior.

---

## Usage

**Plugin:** LENA is already primed when the session opens; **`/lena`** is optional (good for the ritual line).

**Skill-only:** type **`/lena`** in your prompt:

```
/lena
```

On the **first** `/lena` in a thread, LENA answers with something like: **LENA active. What are we building?** After that, same thread keeps LENA routing on every message until **`stop lena`**, **`exit lena`**, or **`lena off`**. With the plugin, the next **new session** primes LENA again via the hook; with skill-only, use **`/lena`** again in the new chat.

### Two quick examples

**Small and clear** (LENA won't over-orchestrate):

```
/lena
> Fix the N+1 query in the user dashboard

→ LENA handles it directly
```

**Big and messy** (LENA will line up the right people):

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

## Rules LENA tries to live by

1. **Correct beats clever.** Always.
2. **If it's vague, LENA asks once.** Not twenty questions. One sharp one.
3. **No scope creep from LENA's side.** LENA builds what you asked.
4. **No half-finished "proof of concept" when you needed something real.**
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

## License

MIT. [justjammin](https://github.com/justjammin).
