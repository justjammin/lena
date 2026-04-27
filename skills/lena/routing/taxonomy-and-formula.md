# LENA Agent Routing

## Contents
- [Signal Taxonomy](#signal-taxonomy)
- [Formula](#formula)
- [Thresholds & Actions](#thresholds--actions)
- [Risk Override Rule](#risk-override-rule)
- [Output Format](#output-format)

---

## Signal Taxonomy

### 1. Task Shape · cap ±6

Detects structural complexity of the request itself.

| Signal | Vote | Weight |
|---|---|---|
| Single sentence | Direct | +2 |
| 3+ sentences | Orchestrate | +1 |
| Question form (what/how/why/…) | Direct | +1 |
| Multi-step connector phrases (and then / after that / step N) | Orchestrate | +1 per, max +2 |
| Extra imperative verbs beyond 1 (build + deploy + test = +2) | Orchestrate | +1 per, max +3 |

### 2. Domain Breadth · cap ±4

Detects cross-stack work. Domains: `frontend`, `backend`, `database`, `devops`, `security`, `ml`.

| Signal | Vote | Weight |
|---|---|---|
| 3+ distinct domains | Orchestrate | +4 |
| 2 distinct domains | Orchestrate | +2 |
| 1 distinct domain | Direct | +2 |
| No domain terms (meta/conversational) | Direct | +1 |

### 3. Concreteness · cap ±4

Detects whether the task is specific or vague.

| Signal | Vote | Weight |
|---|---|---|
| File path present | Direct | +2 |
| Line numbers present | Direct | +1 |
| Quoted string or error message | Direct | +1 |
| Vague goal words without file reference | Orchestrate | +2 |

### 4. Risk · cap D:4 / O:8 (asymmetric by design)

High-risk signals weight Orchestrate more heavily. Destructive ops trigger a hard override.

| Signal | Vote | Weight | Override? |
|---|---|---|---|
| Destructive ops (drop/truncate/wipe/force-push/rm -rf) | Orchestrate | +4 | **Yes** |
| Production context (prod / deploy to prod / push to main) | Orchestrate | +2 | No |
| Security-sensitive terms (password / private key / api key) | Orchestrate | +2 | No |
| Pure read-only intent (list/show/explain/find) with no destructive/prod | Direct | +2 | No |

### 5. Validation Need · cap ±4

Detects whether the task inherently requires a second specialist role.

| Signal | Vote | Weight |
|---|---|---|
| Explicit review/audit/assess request | Orchestrate | +2 |
| Multi-role implied (build AND test AND deploy) | Orchestrate | +2 |
| Explanatory intent (explain / walk me through) | Direct | +2 |

### 6. Intent Verbs · cap ±2

Lightweight scope signal from the user's chosen words.

| Signal | Vote | Weight |
|---|---|---|
| Quick-scope words (just / quick / simple / minor / single) | Direct | +1 per, max +2 |
| Thorough-scope words (complete / comprehensive / system-wide / end-to-end) | Orchestrate | +1 per, max +2 |

---

## Formula

```
net        = total_orchestrate - total_direct
confidence = abs(net) / (total_direct + total_orchestrate) × 100
routing    = "orchestrate"  if net >= 0  else "direct"
```

Tie (net = 0) → Orchestrate. Safer default.

---

## Thresholds & Actions

| Confidence | Action | Behavior |
|---|---|---|
| ≥ 70% | `execute` | Proceed with routing decision |
| 50–69% | `execute_log` | Proceed, mark hat with `*` |
| < 50% | `clarify_or_orchestrate` | Ask one targeted question OR default Orchestrate |
| risk_override | `force_orchestrate` | Skip score entirely → Step 2B |

---

## Risk Override Rule

`risk_override = True` when destructive operation terms are detected:

```
drop table · truncate · hard-reset · force-push · rm -rf · nuke · wipe ·
purge all · delete all · drop db · drop database · delete production
```

When `risk_override` is set, routing is forced to Orchestrate and `action` is `force_orchestrate` regardless of all other signals.

Production and security terms alone raise the Orchestrate score but do not trigger override. Destructive ops always do.

---

## Output Format

```json
{
  "routing": "direct" | "orchestrate",
  "confidence": 0-100,
  "net_score": -N … +N,
  "total_direct": N,
  "total_orchestrate": N,
  "risk_override": true | false,
  "action": "execute" | "execute_log" | "clarify_or_orchestrate" | "force_orchestrate",
  "hat_line": "→ specialist [conf: 82%]",
  "breakdown": {
    "task_shape":      { "direct": N, "orchestrate": N, "signals": [...] },
    "domain_breadth":  { ... },
    "concreteness":    { ... },
    "risk":            { ... },
    "validation_need": { ... },
    "intent_verbs":    { ... }
  }
}
```

Hat line format:
- `→ specialist [conf: 82%]` — high-confidence Direct
- `→ team [conf: 55%*]` — low-confidence Orchestrate (asterisk = below 70%)
- `→ team [risk-override]` — destructive/production ops, confidence not shown

---
