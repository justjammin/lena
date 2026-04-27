# ctx_session — Session State

Intra-session persistence. Survives compaction within a session. Loaded at session start to restore prior run context.

## When to Use vs ctx_knowledge

| Use `ctx_session` | Use `ctx_knowledge` |
|-------------------|---------------------|
| This session's decisions | Facts that persist across many sessions |
| Current task state | Architectural patterns |
| Transient findings | Reusable gotchas |

## Write

```python
ctx_session(action="task",     value="refactoring auth middleware")
ctx_session(action="decision", value="chose Pipeline over Parallel — steps have hard dep chain")
ctx_session(action="finding",  value="backend-developer can own impl+test for small features")
```

## Session Start (Step 1)

```python
ctx_session(action="load")   # restore prior session state (~400 tok)
```

## Session End

```python
ctx_session(action="save")   # persist session state for next run
```

## Fallback (unavailable)

Session start: ask one targeted question for prior context.
During session: record decisions inline as `## Session State` block in response.
