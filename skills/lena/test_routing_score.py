"""
Test suite for routing_score.py

Run: pytest skills/lena/test_routing_score.py -v
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from routing_score import _action, _hat_line, score_task

SCRIPT = Path(__file__).parent / "routing_score.py"


# ── Helpers ──────────────────────────────────────────────────────────────────

def cat(task, category):
    return score_task(task)["breakdown"][category]


# ── _action() ────────────────────────────────────────────────────────────────

class TestAction:
    def test_execute_at_boundary(self):       assert _action(70) == "execute"
    def test_execute_above_70(self):          assert _action(99) == "execute"
    def test_execute_log_at_lower_boundary(self): assert _action(50) == "execute_log"
    def test_execute_log_at_upper_boundary(self): assert _action(69) == "execute_log"
    def test_clarify_just_below_50(self):     assert _action(49) == "clarify_or_orchestrate"
    def test_clarify_at_zero(self):           assert _action(0)  == "clarify_or_orchestrate"


# ── _hat_line() ───────────────────────────────────────────────────────────────

class TestHatLine:
    def test_specialist_high_conf(self):
        assert _hat_line("direct", 82, False) == "→ specialist [conf: 82%]"

    def test_team_high_conf(self):
        assert _hat_line("orchestrate", 75, False, executor="team") == "→ team [conf: 75%]"

    def test_asterisk_at_69(self):
        assert _hat_line("direct", 69, False) == "→ specialist [conf: 69%*]"

    def test_asterisk_at_50(self):
        assert _hat_line("orchestrate", 50, False, executor="team") == "→ team [conf: 50%*]"

    def test_no_asterisk_at_70(self):
        assert "*" not in _hat_line("direct", 70, False)

    def test_risk_override_format(self):
        assert _hat_line("orchestrate", 20, True) == "→ team [risk-override]"

    def test_risk_override_ignores_confidence(self):
        assert _hat_line("orchestrate", 99, True) == "→ team [risk-override]"


# ── Golden tests (pins spec to implementation) ────────────────────────────────

class TestGoldenExamples:
    """Exact matches to worked examples in routing-confidence.md.
    If these fail after a script change, update the spec too."""

    def test_single_file_fix(self):
        r = score_task("fix the null check in auth/middleware.py line 42")
        assert r["routing"]      == "direct"
        assert r["confidence"]   == 56
        assert r["action"]       == "execute_log"
        assert r["risk_override"] is False

    def test_full_auth_build(self):
        r = score_task("build a complete auth system with JWT tokens, test coverage, and deploy to production")
        assert r["routing"]      == "orchestrate"
        assert r["confidence"]   == 64
        assert r["action"]       == "execute_log"
        assert r["risk_override"] is False

    def test_vague_query(self):
        r = score_task("optimize the user query")
        assert r["routing"]    == "direct"
        assert r["confidence"] == 33
        assert r["action"]     == "clarify_or_orchestrate"

    def test_destructive_risk_override(self):
        r = score_task("drop the users table in production and rebuild from the migration")
        assert r["routing"]      == "orchestrate"
        assert r["action"]       == "force_orchestrate"
        assert r["risk_override"] is True

    def test_quick_file_fix(self):
        r = score_task("just add a console.log to debug/auth.js")
        assert r["routing"]    == "direct"
        assert r["confidence"] == 75
        assert r["action"]     == "execute"


# ── task_shape ────────────────────────────────────────────────────────────────

class TestTaskShape:
    def test_single_sentence_votes_direct(self):
        assert cat("fix the login bug", "task_shape")["direct"] >= 2

    def test_question_form_adds_direct(self):
        r = cat("how does the middleware handle errors", "task_shape")
        assert r["direct"] >= 3  # single sentence + question

    def test_multi_step_connector_votes_orchestrate(self):
        assert cat("build the service and then deploy it", "task_shape")["orchestrate"] >= 1

    def test_extra_imperative_verbs_vote_orchestrate(self):
        assert cat("build the API, add tests, and deploy it", "task_shape")["orchestrate"] >= 2

    def test_single_verb_no_orchestrate_penalty(self):
        assert cat("fix the login bug", "task_shape")["orchestrate"] == 0

    def test_file_extension_dot_not_split_sentence(self):
        # "auth/middleware.py" must not split sentence at the dot
        assert cat("fix the bug in auth/middleware.py", "task_shape")["direct"] >= 2


# ── domain_breadth ────────────────────────────────────────────────────────────

class TestDomainBreadth:
    def test_three_domains_max_orchestrate(self):
        r = score_task("build a React frontend with a REST API and postgres database deployed to AWS")
        assert r["breakdown"]["domain_breadth"]["orchestrate"] == 4

    def test_two_domains_votes_orchestrate(self):
        assert cat("add an api endpoint with a sql query", "domain_breadth")["orchestrate"] == 2

    def test_single_domain_votes_direct(self):
        assert cat("optimize this postgres query", "domain_breadth")["direct"] == 2

    def test_no_domain_votes_direct(self):
        assert cat("what should we name this variable", "domain_breadth")["direct"] == 1


# ── concreteness ──────────────────────────────────────────────────────────────

class TestConcreteness:
    def test_file_path_votes_direct(self):
        assert cat("fix the bug in src/auth/login.py", "concreteness")["direct"] >= 2

    def test_line_number_votes_direct(self):
        assert cat("check line 42 in the handler", "concreteness")["direct"] >= 1

    def test_quoted_error_votes_direct(self):
        r = score_task('fix the error "TypeError: cannot read undefined"')
        assert r["breakdown"]["concreteness"]["direct"] >= 1

    def test_vague_without_file_votes_orchestrate(self):
        assert cat("make the app faster", "concreteness")["orchestrate"] == 2

    def test_vague_with_file_no_orchestrate_penalty(self):
        # File reference present → vague penalty suppressed
        assert cat("make src/app.py faster", "concreteness")["orchestrate"] == 0


# ── risk ──────────────────────────────────────────────────────────────────────

class TestRisk:
    @pytest.mark.parametrize("task", [
        "truncate the sessions table",
        "drop the old users table from the database",
        "hard-reset the repo to origin main",
        "force-push to main to rewrite history",
        "run rm -rf on the build directory",
    ])
    def test_destructive_triggers_override(self, task):
        r = score_task(task)
        assert r["risk_override"] is True
        assert r["action"] == "force_orchestrate"
        assert r["routing"] == "orchestrate"

    def test_prod_context_raises_score_no_override(self):
        r = score_task("add a log statement before deploying to production")
        assert r["risk_override"] is False
        assert r["breakdown"]["risk"]["orchestrate"] >= 2

    def test_security_terms_raise_score_no_override(self):
        r = score_task("rotate the api key in settings")
        assert r["risk_override"] is False
        assert r["breakdown"]["risk"]["orchestrate"] >= 2

    def test_readonly_votes_direct(self):
        assert cat("list all routes in the application", "risk")["direct"] == 2

    def test_override_beats_strong_direct_score(self):
        # D heavily favored by file+line+quick — override must still win
        r = score_task("just drop the sessions table in auth/db.py line 5")
        assert r["routing"] == "orchestrate"
        assert r["risk_override"] is True


# ── validation_need ───────────────────────────────────────────────────────────

class TestValidationNeed:
    def test_review_request_votes_orchestrate(self):
        assert cat("do a code review of the payment module", "validation_need")["orchestrate"] >= 2

    def test_audit_votes_orchestrate(self):
        assert cat("audit the auth flow for security issues", "validation_need")["orchestrate"] >= 2

    def test_multi_role_implied_votes_orchestrate(self):
        assert cat("implement the feature with tests", "validation_need")["orchestrate"] >= 2

    def test_explanatory_votes_direct(self):
        assert cat("explain how the middleware pipeline works", "validation_need")["direct"] >= 2


# ── intent_verbs ──────────────────────────────────────────────────────────────

class TestIntentVerbs:
    def test_just_votes_direct(self):
        assert cat("just rename the variable", "intent_verbs")["direct"] >= 1

    def test_quick_votes_direct(self):
        assert cat("quick fix for the header", "intent_verbs")["direct"] >= 1

    def test_comprehensive_votes_orchestrate(self):
        assert cat("do a comprehensive refactor", "intent_verbs")["orchestrate"] >= 1

    def test_end_to_end_votes_orchestrate(self):
        assert cat("build an end-to-end pipeline", "intent_verbs")["orchestrate"] >= 1

    def test_quick_words_capped_at_2(self):
        assert cat("just quick simple small minor single", "intent_verbs")["direct"] <= 2

    def test_thorough_words_capped_at_2(self):
        assert cat("thorough complete comprehensive entire full end-to-end", "intent_verbs")["orchestrate"] <= 2


# ── aggregate / formula ───────────────────────────────────────────────────────

class TestAggregate:
    def test_tie_routes_orchestrate(self):
        # "add a react component that calls an api" →
        # task_shape: +2D (single sentence)
        # domain_breadth: frontend(react) + backend(api) = 2 → +2O
        # net = 0 → tie → Orchestrate
        r = score_task("add a react component that calls an api")
        assert r["net_score"] == 0
        assert r["routing"] == "orchestrate"
        assert r["action"] == "clarify_or_orchestrate"

    def test_net_negative_routes_direct(self):
        r = score_task("just fix the typo in README.md")
        assert r["net_score"] < 0
        assert r["routing"] == "direct"

    def test_net_positive_routes_orchestrate(self):
        r = score_task("build a complete system with tests and deploy to production")
        assert r["net_score"] > 0
        assert r["routing"] == "orchestrate"

    def test_confidence_is_margin_based(self):
        r = score_task("just fix README.md")
        expected = round(abs(r["net_score"]) / (r["total_direct"] + r["total_orchestrate"]) * 100)
        assert r["confidence"] == expected

    def test_output_has_required_keys(self):
        r = score_task("fix the bug")
        required = {
            "routing", "confidence", "net_score", "total_direct",
            "total_orchestrate", "risk_override", "action", "hat_line", "breakdown",
        }
        assert required.issubset(r.keys())

    def test_breakdown_has_all_categories(self):
        r = score_task("fix the bug")
        cats = {"task_shape", "domain_breadth", "concreteness", "risk", "validation_need", "intent_verbs"}
        assert cats.issubset(r["breakdown"].keys())

    def test_confidence_in_valid_range(self):
        for task in ["fix it", "build everything", "drop all tables in prod"]:
            r = score_task(task)
            assert 0 <= r["confidence"] <= 100


# ── edge cases ────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_stdin_returns_error_json(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            input="", capture_output=True, text=True,
        )
        assert result.returncode == 1
        data = json.loads(result.stdout)
        assert "error" in data

    def test_long_input_no_crash(self):
        long_task = "fix the bug " * 500
        r = score_task(long_task)
        assert "routing" in r

    def test_stdin_mode(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            input="fix the typo in README.md",
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert json.loads(result.stdout)["routing"] == "direct"

    def test_cli_arg_mode(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "fix the typo in README.md"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert json.loads(result.stdout)["routing"] == "direct"

    def test_verbose_flag_outputs_plaintext(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--verbose", "fix the bug"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert result.stdout.strip()[0] != "{"  # not JSON

    def test_verbose_contains_routing_line(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--verbose", "fix the bug"],
            capture_output=True, text=True,
        )
        assert "routing" in result.stdout
        assert "confidence" in result.stdout

    def test_json_output_is_valid(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "fix the bug in auth.py"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data["confidence"], int)

    def test_no_recognizable_signals_no_crash(self):
        r = score_task("zxqw frob the blargh")
        assert "routing" in r