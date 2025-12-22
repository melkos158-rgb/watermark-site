# Copilot Prompt Templates for Proofly

## Backend/API Bugfix Template

Act as a senior backend engineer.
Goal: fix bug with minimal changes and no new routes/models.

Context:
- Repo: Proofly (Flask + Blueprints)
- Route: <PASTE ROUTE>
- Expected: <PASTE EXPECTED BEHAVIOR>
- Actual: <PASTE ACTUAL BEHAVIOR>
- Logs/trace: <PASTE STACKTRACE OR LOG SNIPPET>

Rules:
- Root cause first (point to exact line/file)
- Then propose smallest fix
- Do not redirect from API routes; JSON only
- Do not invent models/routes

Output:
1) Cause
2) Patch: exact files + code changes
3) Risk/edge cases
4) How to test (curl + browser steps)

---

## Frontend (templates/JS) Bugfix Template

Act as a senior frontend engineer (JS + Flask templates).
Goal: fix UX bug without changing backend contract.

Context:
- Page: <URL>
- Template(s): <files>
- JS file(s): <files>
- Bug: <what happens>

Rules:
- minimal diff
- no inline JS if not already used
- keep existing CSS classes and DOM structure stable

Output:
1) Cause (DOM selector / event / fetch)
2) Patch (exact selectors + file changes)
3) Expected UX after deploy
4) Quick test checklist
