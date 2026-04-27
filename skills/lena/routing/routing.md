# LENA Agent Routing

## Contents
- [Categories → Agent Types](#categories--agent-types)

---

## Categories → Agent Types

Pick *who* for *what*. One category → several agent types; choose by stack and sub-problem.

| Category | Covers | Default `subagent_type` |
|----------|--------|-------------------------|
| **Architecture** | System design, tradeoffs | `architect-reviewer` |
| **Implementation** | Writing and modifying code | `backend-developer`, `frontend-developer`, `fullstack-developer`, `refactoring-specialist` |
| **Debugging** | Root cause analysis | `debugger` (diagnosis, repro, trace); `error-detective` (logs, correlation, failure patterns) |
| **Code Review** | Quality and correctness | `code-reviewer` (maintainability, bugs, API shape) |
| **Performance** | Optimization | `dx-optimizer` (builds, workflow, dev loop); pair with **Database** when bottleneck is queries |
| **Testing** | Test generation | `test-automator` |
| **Security** | Vulnerabilities, secure design | `code-reviewer` — state **security focus** explicitly in prompt (threat model, OWASP, auth/data) |
| **Database** | Schema, queries, data layer | `database-administrator` (schema, replication); `database-optimizer` (slow queries, indexes); `postgres-pro` when PostgreSQL-specific |
| **DevOps** | Deployment and infrastructure | `cloud-architect`; `kubernetes-specialist` for K8s |
| **Documentation** | Explanations and docs | `documentation-engineer`; `technical-writer` for reference/API prose |

**ML/AI lane:** `llm-architect` (pipelines, RAG, tuning, serving). Treat as own lane alongside Implementation / Architecture.

**Routing discipline:** Don't spawn agents for categories user didn't need. Combine steps when one agent can own two adjacent categories without losing quality (e.g. small feature: Implementation + Testing only).
