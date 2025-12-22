# Top-1 Audit

## What is Top-1 Audit?
A one-command, production-grade terminal audit for your Flask/Python project. It checks your environment, dependencies, code quality, security, and auto-fixes what is safe. All results are saved to a timestamped report in the `reports/` folder.

## How to Run Top-1 Audit

### Windows (PowerShell)
1. Activate your Python virtual environment:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```
2. Run the audit:
   ```powershell
   .\tools\top1_audit.ps1
   ```

### Linux/macOS (bash)
1. Activate your Python virtual environment:
   ```bash
   source .venv/bin/activate
   ```
2. Run the audit:
   ```bash
   bash tools/top1_audit.sh
   ```

## Output
- A full audit report is saved to `reports/top1_audit_<yyyy-mm-dd_hhmm>.txt`.
- The script will exit with a non-zero code if any critical errors are found (syntax, pip check, vulnerabilities, or unfixable lint errors).

## What does it check?
- venv activation
- Python version
- Syntax/indentation errors (compileall)
- Dependency health (`pip check`, `pip list --outdated`)
- Flask routes (if app imports)
- Flask-Migrate status (if present)
- Security audit (`pip-audit`)
- Lint/format auto-fix (ruff, black, isort, autoflake)
- Type check (mypy, if config present)

## Notes
- All audit reports are saved in the `reports/` directory (not committed to git).
- No runtime code is modified except for auto-fixes (formatting, unused imports, etc).
- For best results, always activate your venv before running the audit.
