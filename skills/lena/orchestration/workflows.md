# Execution Patterns + Workflow Composition

## Patterns

| Pattern | Use when | Key trait |
|---------|----------|-----------|
| **Router** | Single domain, one agent | Go to [Step 3A](../SKILL.md) in — no spawning |
| **Pipeline** | Steps ordered, each feeds next | Sequential; output N → input N+1 via context |
| **Parallel** | 2+ steps, zero inter-dep | Run simultaneously; aggregator merges |
| **Feedback Loop** | Output quality critical | Generator + Critic loop until threshold |
| **Supervisor** | Multi-step, order dynamic | LENA decides next agent from prior output |
| **Plan Then Execute** | Complex or ambiguous scope | Decompose fully before any execution |
| **Hierarchical** | Large scope, clear domain split | Domain managers + workers |
| **Shared Memory** | Long-running or stateful | All agents read/write `ctx_knowledge`; no direct agent-to-agent calls |

## Pattern Combinations

- `Plan Then Execute + Parallel` — plan first, run independent steps simultaneously
- `Hierarchical + Feedback Loop` — manager delegates, worker output through critic before returning
- `Pipeline + Shared Memory` — fixed sequence where each agent enriches shared `ctx_knowledge`

## Parallel Dispatch Rules

- Identify independent steps explicitly before dispatch
- Pass compressed context block to each parallel agent — not raw history
- Skip hat file writes during parallel steps — concurrent writes corrupt hat state
- Aggregator always runs sequentially after all parallel agents complete

## Step 4B — Complex Graph Decomposition

When decomposition has 4+ steps, non-obvious dep edges, Plan Then Execute, Hierarchical pattern, or prior run failed due to bad wiring — **fully plan before creating any `bd` issues**.

Write out complete execution plan first:
```
Step 1: <title> — <category> — <agent> — depends on: none
Step 2: <title> — <category> — <agent> — depends on: Step 1
Step 3: <title> — <category> — <agent> — depends on: Step 2
...
```

Verify: every dep edge stated, output shape of N matches input expectation of N+1, no circular deps. Only proceed to `bd create` commands after plan confirmed correct.
