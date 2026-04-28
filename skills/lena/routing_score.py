#!/usr/bin/env python3
"""
LENA routing confidence scorer.
Zero LLM calls. Deterministic text heuristics only.

Usage:
    python routing_score.py "task text here"
    echo "task text" | python routing_score.py
    python routing_score.py --verbose "task text"
"""

from __future__ import annotations
import json
import re
import sys
from dataclasses import dataclass, field


@dataclass
class CategoryScore:
    direct: int = 0
    orchestrate: int = 0
    signals: list[str] = field(default_factory=list)

    def add_direct(self, pts: int, note: str) -> None:
        self.direct += pts
        self.signals.append(f"{note} (+{pts}D)")

    def add_orchestration(self, pts: int, note: str) -> None:
        self.orchestrate += pts
        self.signals.append(f"{note} (+{pts}O)")


def _find(pattern: str, text: str) -> list[str]:
    return re.findall(pattern, text, re.IGNORECASE)


def _suggest_role(task: str, domains: list[str], imp_verbs: set[str]) -> str:
    t = task.lower()

    # Error/exception signals — check before generic debug
    if re.search(r"\b(typeerror|valueerror|exception|traceback|stack trace|500|undefined is not|cannot read)\b", t):
        if re.search(r"\b(correlate|across service|pattern|root cause.*multiple)\b", t):
            return "error-detective"
        return "debugger"

    if "debug" in imp_verbs or re.search(r"\b(bug|broken|not working|failing|error|crash)\b", t):
        return "debugger"

    # Code quality
    if re.search(r"\b(security review|vulnerability|owasp|injection|xss|csrf)\b", t):
        return "code-reviewer"

    if re.search(r"\b(review|audit|code review|second opinion)\b", t):
        return "code-reviewer"

    if "refactor" in imp_verbs:
        return "refactoring-specialist"

    # Architecture/design
    if re.search(r"\b(architect|system design|diagram|pattern|trade.?off|adr)\b", t):
        return "architect-reviewer"

    # Testing
    if "test" in imp_verbs or re.search(r"\b(spec|unit test|integration test|e2e|test coverage)\b", t):
        return "test-automator"

    # ML/AI
    if "ml" in domains:
        return "ml-engineer"

    # Database
    if "database" in domains and "backend" not in domains:
        return "database-optimizer"

    # DevOps/infra
    if "devops" in domains:
        return "cloud-architect"

    # Frontend only
    if "frontend" in domains and "backend" not in domains:
        return "frontend-developer"

    # Both → fullstack
    if "frontend" in domains and "backend" in domains:
        return "fullstack-developer"

    # Backend only
    if "backend" in domains:
        return "backend-developer"

    # Docs/writing
    if "write" in imp_verbs or re.search(r"\b(document|docs|readme|guide|tutorial)\b", t):
        return "technical-writer"

    # Analysis/explain
    if re.search(r"\b(explain|analyze|why|how does|what is|describe)\b", t):
        return "architect-reviewer"

    return "backend-developer"


def score_task(task: str) -> dict:
    t = task.lower()
    cats: dict[str, CategoryScore] = {
        "task_shape":      CategoryScore(),
        "domain_breadth":  CategoryScore(),
        "concreteness":    CategoryScore(),
        "risk":            CategoryScore(),
        "validation_need": CategoryScore(),
        "intent_verbs":    CategoryScore(),
    }

    # ── Task Shape ──────────────────────────────────────────────────────────────
    ts = cats["task_shape"]

    # Split on sentence-ending punctuation but NOT on "." inside filenames/decimals
    sentences = [s.strip() for s in re.split(r"[!?]|\.\s+", task) if s.strip()]
    if len(sentences) == 1:
        ts.add_direct(2, "single sentence")
    elif len(sentences) >= 3:
        ts.add_orchestration(1, f"{len(sentences)} sentences")

    if re.match(r"^\s*(what|how|why|where|when|is|are|does|can|should)\b", t):
        ts.add_direct(1, "question form")

    connectors = _find(
        r"\b(and then|after that|additionally|furthermore|step \d|first[, ]+then|once that[, ]+)\b", t
    )
    if connectors:
        pts = min(2, len(connectors))
        ts.add_orchestration(pts, f"multi-step connectors: {connectors[:3]}")

    imp_verbs = set(_find(
        r"\b(build|create|implement|deploy|test|review|refactor|migrate|audit|integrate|"
        r"add|fix|debug|analyze|design|update|remove|delete|configure|write|generate|scaffold)\b", t
    ))
    extra = max(0, len(imp_verbs) - 1)
    if extra:
        pts = min(3, extra)
        ts.add_orchestration(pts, f"extra imperative verbs: {sorted(imp_verbs)}")

    # ── Domain Breadth ──────────────────────────────────────────────────────────
    db = cats["domain_breadth"]

    domain_patterns = {
        "frontend": r"\b(css|html|react|vue|angular|svelte|jsx|tsx|dom|browser|component|stylesheet)\b",
        "backend":  r"\b(api|endpoint|service|server|controller|middleware|route|handler|rest|graphql|grpc)\b",
        "database": r"\b(sql|query|schema|migration|index|table|database|\bdb\b|orm|postgres|mysql|mongo|redis)\b",
        "devops":   r"\b(deploy|docker|kubernetes|k8s|\bci\b|\bcd\b|pipeline|infra|cloud|aws|gcp|azure|terraform)\b",
        "security": r"\b(auth|oauth|jwt|permission|role|acl|encrypt|decrypt|credential|secret|\bcert\b)\b",
        "ml":       r"\b(model|training|inference|embedding|\bllm\b|fine.?tun|rag|vector|neural|dataset)\b",
    }
    domains = [d for d, p in domain_patterns.items() if re.search(p, t)]

    if len(domains) >= 3:
        db.add_orchestration(4, f"3+ domains: {domains}")
    elif len(domains) == 2:
        db.add_orchestration(2, f"2 domains: {domains}")
    elif len(domains) == 1:
        db.add_direct(2, f"single domain: {domains}")
    else:
        db.add_direct(1, "no domain terms — meta/conversational")

    # ── Concreteness ────────────────────────────────────────────────────────────
    con = cats["concreteness"]

    if re.search(r"[\w/\-]+\.\w{2,5}(?:\s|:|$|,|')", task):
        con.add_direct(2, "file path present")

    if re.search(r"\bline[s]?\s+\d+|:\d{2,}", t):
        con.add_direct(1, "line numbers present")

    if re.search(r'"[^"]{8,}"|\'[^\']{8,}\'|`[^`]{8,}`', task):
        con.add_direct(1, "quoted string/error present")

    vague = _find(r"\b(better|improve|enhance|optimize|cleaner|nicer|more efficient|faster)\b", t)
    has_file = bool(re.search(r"[\w/\-]+\.\w{2,5}", task))
    if vague and not has_file:
        con.add_orchestration(2, f"vague goal without specifics: {vague}")

    # ── Risk (asymmetric — O ceiling higher by design) ──────────────────────────
    risk = cats["risk"]
    risk_override = False

    _destructive_patterns = [
        r"\bdrop\b.{0,40}\b(table|database|db|column|index|schema)\b",
        r"\btruncate\b",
        r"\bhard.?reset\b",
        r"\bforce.?push\b",
        r"\brm\s*-rf\b",
        r"\bnuke\b",
        r"\bwipe\b",
        r"\bpurge all\b",
        r"\bdelete all\b",
        r"\bdelete.*production\b",
    ]
    destructive = [p for p in _destructive_patterns if re.search(p, t)]
    if destructive:
        risk.add_orchestration(4, f"destructive ops matched: {len(destructive)} pattern(s)")
        risk_override = True

    prod_ctx = _find(r"\b(prod|production|live site|push to main|deploy to prod|release to)\b", t)
    if prod_ctx:
        risk.add_orchestration(2, f"production context: {prod_ctx}")

    sec_terms = _find(
        r"\b(password|credentials?|private key|api key|access key|oauth secret|signing key)\b", t
    )
    if sec_terms:
        risk.add_orchestration(2, f"security-sensitive: {sec_terms}")

    readonly = _find(
        r"\b(list|show|explain|read|check|view|display|describe|what is|how does|find|search|look up)\b", t
    )
    if readonly and not destructive and not prod_ctx:
        risk.add_direct(2, f"read-only intent: {readonly[:3]}")

    # ── Validation Need ──────────────────────────────────────────────────────────
    val = cats["validation_need"]

    review_terms = _find(r"\b(review|audit|code review|security review|second opinion|verify quality|assess)\b", t)
    if review_terms:
        val.add_orchestration(2, f"review/audit needed: {review_terms}")

    multi_role = _find(r"\b(then test|and review|plus document|also review|with tests|with docs|and deploy)\b", t)
    if multi_role:
        val.add_orchestration(2, f"multi-role implied: {multi_role}")

    explain_terms = _find(r"\b(explain|what is|how does|walk me through|help me understand|describe how)\b", t)
    if explain_terms:
        val.add_direct(2, f"explanatory intent: {explain_terms}")

    # ── Intent Verbs ─────────────────────────────────────────────────────────────
    iv = cats["intent_verbs"]

    quick = _find(r"\b(just|quick|simple|small|minor|briefly|one.liner|single|only)\b", t)
    if quick:
        pts = min(2, len(quick))
        iv.add_direct(pts, f"quick intent: {quick}")

    thorough = _find(r"\b(thorough|complete|full|entire|comprehensive|system.wide|end.to.end|all of)\b", t)
    if thorough:
        pts = min(2, len(thorough))
        iv.add_orchestration(pts, f"thorough intent: {thorough}")

    # ── Aggregate ─────────────────────────────────────────────────────────────────
    total_d = sum(c.direct for c in cats.values())
    total_o = sum(c.orchestrate for c in cats.values())
    net = total_o - total_d
    total = total_d + total_o
    confidence = round(abs(net) / total * 100) if total > 0 else 0

    if risk_override:
        routing = "orchestrate"
        action = "force_orchestrate"
    elif net > 0:
        routing = "orchestrate"
        action = _action(confidence)
    elif net < 0:
        routing = "direct"
        action = _action(confidence)
    else:
        routing = "orchestrate"  # tie → safer default
        action = "clarify_or_orchestrate"

    suggested_role = _suggest_role(task, domains, imp_verbs) if routing == "direct" else None

    # executor: who actually runs the work
    # "self"  — LENA wears the hat (clear scope, single domain, or file-anchored)
    # "agent" — spawn a specialist agent (direct but genuinely cross-domain, no file anchor)
    # "team"  — orchestrate multiple agents
    has_file_anchor = bool(re.search(r"[\w/\-]+\.\w{2,5}", task))
    if routing == "orchestrate":
        executor = "team"
    elif routing == "direct" and len(domains) >= 3 and not has_file_anchor:
        executor = "agent"  # 3+ domains, no file anchor → delegate to specialist
    else:
        executor = "self"

    return {
        "routing": routing,
        "confidence": confidence,
        "net_score": net,
        "total_direct": total_d,
        "total_orchestrate": total_o,
        "risk_override": risk_override,
        "action": action,
        "suggested_role": suggested_role,
        "executor": executor,
        "hat_line": _hat_line(routing, confidence, risk_override, suggested_role, executor),
        "step3a_prompt": (
            f"Act as {suggested_role}. Claim bd ticket, write '{suggested_role}' to .lena-hat, execute."
            if executor == "self" and suggested_role else None
        ),
        "breakdown": {
            cat: {
                "direct": c.direct,
                "orchestrate": c.orchestrate,
                "signals": c.signals,
            }
            for cat, c in cats.items()
        },
    }


def _action(confidence: int) -> str:
    if confidence >= 70:
        return "execute"
    if confidence >= 50:
        return "execute_log"
    return "clarify_or_orchestrate"


def _hat_line(routing: str, confidence: int, override: bool, role: str | None = None, executor: str = "self") -> str:
    if override:
        return "→ team [risk-override]"
    suffix = "*" if confidence < 70 else ""
    if executor == "team":
        display = "team"
    elif executor == "agent":
        display = f"agent:{role or 'specialist'}"
    else:
        display = role or "specialist"
    return f"→ {display} [conf: {confidence}%{suffix}]"


def _verbose(result: dict) -> str:
    lines = [
        f"routing      : {result['routing']}",
        f"confidence   : {result['confidence']}%",
        f"net score    : {result['net_score']} "
        f"(D={result['total_direct']} O={result['total_orchestrate']})",
        f"action       : {result['action']}",
        f"suggested role: {result['suggested_role']}",
        f"hat line     : {result['hat_line']}",
        f"step3a prompt: {result['step3a_prompt']}",
        "",
        "breakdown:",
    ]
    for cat, data in result["breakdown"].items():
        if data["direct"] or data["orchestrate"] or data["signals"]:
            lines.append(f"  {cat:<18} D={data['direct']} O={data['orchestrate']}")
            for sig in data["signals"]:
                lines.append(f"    · {sig}")
    return "\n".join(lines)


if __name__ == "__main__":
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    args = [a for a in sys.argv[1:] if a not in ("--verbose", "-v")]

    task_text = " ".join(args) if args else sys.stdin.read().strip()
    if not task_text:
        print(json.dumps({"error": "no task text provided"}))
        sys.exit(1)

    result = score_task(task_text)

    if verbose:
        print(_verbose(result))
    else:
        print(json.dumps(result, indent=2))