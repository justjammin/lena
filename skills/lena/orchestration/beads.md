# Beads — Persistent Task Tracking

Dolt-backed graph issue tracker. Survives compaction. `bd ready` auto-excludes blocked tasks. `bd prime` injects AI-optimized context on SessionStart + PreCompact automatically.

## Initialization

`bd init` — run once by human, not agent.
`bd setup claude` — wires SessionStart/PreCompact hooks.

## Orchestration Pattern

```bash
# Register all steps upfront with dep edges
bd create "Design API contracts" -t task -p 1 --json
bd create "Implement endpoints"  -t task -p 1 --deps blocks:<bd-1> --json
bd create "Write tests"          -t task -p 2 --deps blocks:<bd-2> --json

# Execute
bd update <bd-1> --claim --json
# … delegate to agent …
bd close <bd-1> --reason "contracts finalized" --json
# Retain key output in LENA context — inject manually into next prompt

bd ready --json   # returns bd-2 (now unblocked)
bd update <bd-2> --claim --json
# pass prior output under ## Context from upstream steps in agent prompt

# Verify
bd dep tree <parent-id>
bd list --status open --json
bd list --status in_progress --json
```

## Output Propagation

Beads does not auto-inject upstream output. LENA retains key output from closed step in context; manually injects under `## Context from upstream steps` in next agent prompt.

## Discovered Work Mid-Task

```bash
bd create "Found edge case" -t bug -p 1 --deps discovered-from:<current-id> --json
```

## Blocked Task

```bash
bd update <id> --status blocked --description "bad output: ..."
```

## Fallback (bd unavailable)

Numbered checklist inline. Note outputs as code blocks after each step. Pass manually into each subsequent agent prompt.
