# Knowledge Consolidation

## When to Consolidate

- Session end (always)
- After major architectural decision block
- After orchestrated run producing durable knowledge

## Protocol

```python
# 1. Promote session findings → permanent facts
ctx_knowledge(action="consolidate")

# 2. Persist session state for next run
ctx_session(action="save")
```

## What to Persist

**Keep:**
- Architectural decisions and rationale
- Patterns that improved agent routing
- Gotchas encountered + resolutions
- Agent capability findings (e.g. "backend-developer owns impl+test for small features")
- Graph findings that took non-trivial queries to produce — key hub nodes, surprising connections, architectural paths — tag `[graph:HEAD]` so staleness is detectable

**Drop:**
- Step-level execution details
- Per-run outputs already reflected in code
- Intermediate findings superseded by later decisions

## One Source of Truth

Never write same fact to both `ctx_knowledge` AND `ctx_session`. `ctx_knowledge` wins for anything worth keeping beyond current session.
