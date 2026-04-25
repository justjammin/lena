---
name: weave
description: >
  Execution graph layer for the LENA harness. Manages task state across orchestrated
  multi-agent runs with structured input/output context propagation between steps.
  Data flows through the dependency graph: each task's output becomes the next task's
  input automatically. Model-agnostic — any LLM backend reads JSON via wv ready --json.
  Use during Step 2B orchestration with 2+ sub-agent steps.
---

# Weave — Execution Graph for the LENA Harness

Weave is the state layer that turns LENA's decomposed plans into a live execution graph.
Tasks are nodes. Dependencies are directed edges. Outputs from one step flow as inputs
to the next. Any model reads the graph via `wv ready --json` and acts on what it gets.

## What makes Weave different

- **Data flow, not just status** — `wv done <id> --output <json>` persists results;
  `wv ready` injects upstream outputs into the next task's `input` blob automatically
- **Model-agnostic** — Weave is a JSON state store; the model is whoever calls it
- **DAG-native** — `wv graph` renders the execution tree; `depends_on` drives ordering
  and context wiring, not just sequencing

## Setup

Before first use in a session:

```bash
wv ready --json 2>/dev/null || wv init
```

## The harness loop

```
decompose goal
  → wv create each step (with deps)
  → wv ready --json          # get next task + injected upstream context
  → wv claim <id>            # mark in_progress
  → delegate to agent        # pass task.title + task.input as context
  → wv done <id> --output '{"key":"value"}'   # persist result
  → wv ready --json          # repeat until null
```

## Core workflow

```bash
# 1. Decompose: push each step as a task
wv create "Design auth schema" --agent architect-reviewer --priority 1
wv create "Implement JWT logic" --agent backend-developer --priority 1 --depends wv-1
wv create "Write auth tests"   --agent test-automator    --priority 2 --depends wv-2
wv create "API docs"           --agent technical-writer  --priority 3 --depends wv-2

# 2. Inspect the graph
wv graph

# 3. Execute loop
TASK=$(wv ready --json)
wv claim $(echo $TASK | jq -r .id)

# 4. Agent runs. Capture output.
wv done wv-1 --output '{"schema":"users(id,email,hash)","algo":"RS256"}'

# 5. Next task picks up context automatically
wv ready --json
# → wv-2 now has input["wv-1"] = {"schema":"...","algo":"..."}

# 6. Repeat until null
```

## Commands

| Command | Description |
|---------|-------------|
| `wv init [prefix]` | Initialize `.weave/` in current project |
| `wv create "title" [opts]` | Create task node, returns ID |
| `wv ready [--agent A]` | Surface next unblocked task + upstream context |
| `wv claim <id>` | Mark `in_progress` |
| `wv done <id> [--output '{}']` | Mark done, persist output blob |
| `wv block <id> [--notes text]` | Mark blocked with reason |
| `wv list [--status S] [--agent A]` | List tasks with filters |
| `wv show <id>` | Full task detail with input/output |
| `wv update <id> [opts]` | Update any field |
| `wv graph` | Render execution DAG |
| `wv stats` | Counts by status |

All commands: append `--json` for structured output.

## Task schema

```json
{
  "id": "wv-1",
  "title": "Design auth schema",
  "agent": "architect-reviewer",
  "status": "pending",
  "priority": 1,
  "depends_on": [],
  "parent": null,
  "notes": "",
  "input": {},
  "output": {},
  "created": "ISO8601",
  "updated": "ISO8601"
}
```

**Status values:** `pending` → `in_progress` → `done` | `blocked`
**Priority:** `0` critical · `1` high · `2` medium (default) · `3` low

## Data flow mechanics

`depends_on` does two things:
1. Blocks the task from appearing in `wv ready` until all deps are done
2. Propagates each done dep's `output` blob into the task's `input` map

```bash
wv done wv-1 --output '{"decisions":"JWT RS256","schema":"users(id,email)"}'
wv ready --json
# task.input = { "wv-1": { "decisions": "JWT RS256", "schema": "..." } }
```

The agent receiving the task always gets full upstream context without manual wiring.

## Embedding context in agent prompts

When delegating a step to a sub-agent, inject `task.input` explicitly:

```
## Task
${task.title}

## Context from upstream steps
${JSON.stringify(task.input, null, 2)}
```

This is the harness's job — Weave supplies the data, LENA formats it, the model acts on it.

## LENA integration (Step 2B)

At the start of any orchestrated execution with 2+ steps:

```bash
# Check Weave is ready
wv ready 2>/dev/null || wv init

# Push decomposed steps
wv create "..." --agent <role> --priority <N> [--depends <ids>]

# Execute loop
while true; do
  TASK=$(wv ready --json)
  [ "$TASK" = "null" ] && break
  ID=$(echo $TASK | jq -r .id)
  wv claim $ID
  # delegate to agent with task + input context
  # capture output
  wv done $ID --output '<agent result json>'
done

wv stats
```

## Fallback (wv not installed)

Maintain a numbered checklist in the active response. Note input/output manually as
code blocks. Update status inline. Resume with Weave on next session.

## LLM-agnostic contract

Weave has no knowledge of which model processes a task. The contract:

1. Caller runs `wv ready --json` — gets task with `input` already populated
2. Caller passes `task.title` + `task.input` to any model (Claude, GPT-4o, Qwen3, local)
3. Model produces output; caller runs `wv done <id> --output '<json>'`
4. Weave propagates to downstream tasks

Swap the model. The graph doesn't change.
