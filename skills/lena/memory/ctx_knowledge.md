# ctx_knowledge — Cross-Session Facts

Persistent, contradiction-detected key-value store. Survives compaction. Semantic recall via `action="recall"`.

## Write

```python
# Atomic fact
ctx_knowledge(action="remember", category="architecture",
              key="auth-method", value="JWT, stateless, refresh via /auth/refresh")

# Convention or pattern
ctx_knowledge(action="pattern", key="pipeline-decomp",
              value="Use weave-planner for 4+ step graphs with dependency edges",
              pattern_type="structure")

# Gotcha — prevent repeating mistakes
ctx_knowledge(action="gotcha", severity="warning",
              trigger="bd init on nested dir",
              resolution="bd init anchors to git root — run from repo root")
```

## Recall

```python
ctx_knowledge(action="recall", query="auth approach")      # semantic search
ctx_knowledge(action="recall", query="bd gotchas")         # pull warnings
ctx_knowledge(action="timeline", category="architecture")  # fact version history
ctx_knowledge(action="wakeup")                             # compact project briefing (session start)
```

## Consolidate (Session End)

```python
ctx_knowledge(action="consolidate")  # extract session findings → persistent facts
```

## Repo Analysis (HEAD-keyed)

```python
result = ctx_knowledge(action="recall", query="repo:overview")
head   = ctx_shell("git rev-parse --short=6 HEAD")
if not result or head not in result:
    arch  = ctx_architecture(action="overview", root=".")
    graph = ctx_graph(action="build", project_root=".")
    ctx_knowledge(action="remember", category="architecture",
                  key="repo:overview", value=f"{arch} | head:{head}")
```

## Fallback (unavailable)

During session: `## Session Memory` scratchpad block in response.
Session end: 3–5 bullet summary, offer to save as file.
