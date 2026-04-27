# Agent Execution Loop

7-step orchestration loop for Step 3B. Read [workflows.md](workflows.md) for pattern selection first.

## Contents
- [Execution Steps](#execution-steps)
- [Context Compression](#context-compression)
- [Excellence Gate](#excellence-gate)

---

## Execution Steps

1. **Classify by category + register domain tickets.**
   ```bash
   bd create "<Category>: <task>" -t task -p 1 --deps blocks:<step-2b-id> --json
   ```
   One per category. Becomes parent node for step-level tasks in step 5.

2. **Map to available agents.** Read live allowed agent list. Discover custom agents from disk (YAML frontmatter in `{workspace}/.claude/agents/`, `~/.claude/agents/`). Merge with table in [../routing/routing.md](../routing/routing.md). Team composition: parallel steps → diverse specialists, no overlapping domains. Critical path → narrower agents over generalists.

3. **Select pattern.** See [workflows.md](workflows.md). State choice in decomposition.

4. **State decomposition.** Pattern chosen, ordered steps, category per step, delegate id per step.

4B. **Complex graphs: write full plan inline first.** See [workflows.md](workflows.md) Step 4B.

> **Planning ends here. Step 5 is first execution action.**

5. **Register ALL steps in Beads — FIRST. No exceptions.**
   ```bash
   bd dep tree <parent-id>        # verify dependency tree
   bd list --status open --json   # confirm all tasks pending
   ```
   > **HARD GATE:** No Agent tool call until `bd list --status open` confirms all steps registered. bd unavailable → inline checklist fallback, state explicitly — do not silently skip.

6. **Execute the loop.**
   - `bd update <id> --claim --json` — mark in_progress before delegating
   - **Compress context** (see [Context Compression](#context-compression)) before each sub-agent call
   - Delegate to agent. Inject prior step output under `## Context from upstream steps`
   - `bd close <id> --reason "<summary>" --json` — mark complete. Retain key output in LENA context
   - `bd ready --json` — find next unblocked task
   - **Validate:** output non-empty and coherent before dispatching next dependent step. Malformed → `bd update <id> --status blocked --description "bad output: ..."` and escalate
   - **Dynamic adaptation:** step fails or scope expands → re-evaluate graph. Reroute, drop step, or switch pattern. Create new bd issues or close obsolete ones to reflect updated plan

7. **Synthesize + close.**
   ```bash
   bd list --status open --json        # any unclosed?
   bd list --status in_progress --json # still running?
   ```
   - All outputs integrated — no step silently dropped
   - Errors resolved or explicitly deferred
   - Key decisions → `ctx_knowledge` or `ctx_session`
   - New patterns → `ctx_knowledge(action="pattern", ...)`

   ```
   Orchestration complete. [N] agents · [M] tasks · pattern: [chosen] · [X]/[M] first-pass.
   [One line: what was produced, notable decision or deviation.]
   ```

Typical category order: **Architecture** → **Implementation** → **Debugging** → **Testing** / **Code Review** / **Security** / **Documentation**

---

## Context Compression

Before each sub-agent delegation in Step 6:
- Extract: task goal, decisions so far, current step output, blocking facts
- Inject as `## Context` at top of agent prompt
- Cap at 500 tokens — do not dump raw conversation history
- After step completes, update compressed context with step output

---

## Excellence Gate

Pre-synthesis check (Step 7):
- All bd tasks closed? (`bd list --status open`)
- No step's output silently dropped from synthesis
- Errors resolved or deferred with explicit note
- Durable knowledge written to `ctx_knowledge`/`ctx_session`
- New patterns or gotchas recorded
