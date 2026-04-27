# Task Classification — Edge Cases

## Mixed Signals

When signals conflict (e.g. "one domain" but "ambiguous scope"):

- Default to **Orchestrate** if any signal is uncertain
- Direct path only when ALL signals clearly point that way
- "Looks simple" is not a signal — scope-expand risk overrides assumption

## Ambiguous / Exploratory

"What could we do about X?" / "How should we approach this?" → **Direct**
- Answer in 2-3 sentences: recommendation + tradeoff
- Do not implement. Wait for user to agree.
- Hat: `architect-reviewer` or closest fit

"Build me a system for X" with no spec → **Orchestrate** via Plan Then Execute
- First step: clarify requirements before decomposing

## Scope Expansion Mid-Execution

Task classified Direct but grows during work:
1. Stop current step
2. Re-classify as Orchestrate, state why
3. Register remaining work in Beads
4. Resume from orchestrated mode

## Router Pattern

Step 3B analysis reveals single best agent owns entire task end-to-end → go back to Step 3A.
- Don't spawn for single-agent work
- Direct execution always preferred over spawning when one agent can own it
