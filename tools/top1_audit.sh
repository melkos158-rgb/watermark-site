#!/bin/bash
# tools/top1_audit.sh
# Top-1 Quality Terminal Audit for Flask/Python projects (Linux/macOS)
# Usage: bash tools/top1_audit.sh

set -euo pipefail
start_time=$(date '+%Y-%m-%d %H:%M')
timestamp=$(date '+%Y-%m-%d_%H%M')
report_dir="$(dirname "$0")/../reports"
report_path="$report_dir/top1_audit_$timestamp.txt"
mkdir -p "$report_dir"
echo "Top-1 Audit started: $start_time" > "$report_path"

section() {
  echo -e "\n==== $1 ====" | tee -a "$report_path"
}

sub() {
  echo "-- $1" | tee -a "$report_path"
}

section "VENV CHECK"
if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  echo "WARNING: Python venv is not active! Activate your venv before running the audit." | tee -a "$report_path"
else
  sub "Venv: $VIRTUAL_ENV"
fi

section "PYTHON VERSION"
pyexe=$(command -v python3 || command -v python)
pyver=$($pyexe --version 2>&1)
sub "Python: $pyexe"
sub "Version: $pyver"

section "COMPILE: python -m compileall -q ."
if ! $pyexe -m compileall -q . 2>&1 | tee -a "$report_path"; then
  echo "CRITICAL: Compile failed. See report." | tee -a "$report_path"
  exit 2
fi

section "PIP CHECK"
if ! $pyexe -m pip check 2>&1 | tee -a "$report_path"; then
  echo "CRITICAL: pip check failed." | tee -a "$report_path"
  exit 3
fi

section "PIP OUTDATED"
$pyexe -m pip list --outdated 2>&1 | tee -a "$report_path"

section "FLASK ROUTES"
if $pyexe -c "import app" 2>/dev/null; then
  $pyexe -m flask --app app routes 2>&1 | tee -a "$report_path"
else
  echo "Flask app import failed, skipping routes." | tee -a "$report_path"
fi

section "FLASK-MIGRATE"
if $pyexe -c "import flask_migrate" 2>/dev/null; then
  $pyexe -m flask --app app db current 2>&1 | tee -a "$report_path"
  $pyexe -m flask --app app db check 2>&1 | tee -a "$report_path"
else
  echo "Flask-Migrate not present, skipping." | tee -a "$report_path"
fi

section "SECURITY: pip-audit"
if ! $pyexe -m pip show pip-audit >/dev/null 2>&1; then
  sub "Installing pip-audit..."
  $pyexe -m pip install pip-audit | tee -a "$report_path"
fi
if ! pip-audit 2>&1 | tee -a "$report_path"; then
  echo "CRITICAL: Vulnerabilities found by pip-audit!" | tee -a "$report_path"
  exit 4
fi

section "LINT/FIX: ruff, black, isort, autoflake"
for tool in ruff black isort autoflake; do
  if ! $pyexe -m pip show $tool >/dev/null 2>&1; then
    sub "Installing $tool..."
    $pyexe -m pip install $tool | tee -a "$report_path"
  fi
done
ruff check . --fix 2>&1 | tee -a "$report_path"
black . 2>&1 | tee -a "$report_path"
isort . 2>&1 | tee -a "$report_path"
autoflake --in-place --recursive --remove-all-unused-imports --remove-unused-variables . 2>&1 | tee -a "$report_path"

section "RE-COMPILE AFTER FIXES"
if ! $pyexe -m compileall -q . 2>&1 | tee -a "$report_path"; then
  echo "CRITICAL: Compile failed after auto-fixes. See report." | tee -a "$report_path"
  exit 5
fi

section "OPTIONAL: MYPY TYPE CHECK"
if [[ -f mypy.ini || -f pyproject.toml ]]; then
  if ! $pyexe -m pip show mypy >/dev/null 2>&1; then
    sub "Installing mypy..."
    $pyexe -m pip install mypy | tee -a "$report_path"
  fi
  mypy . 2>&1 | tee -a "$report_path"
else
  sub "No mypy config found, skipping type check."
fi

end_time=$(date '+%Y-%m-%d %H:%M')
echo -e "\n==== AUDIT COMPLETE ====" | tee -a "$report_path"
echo "Started: $start_time" | tee -a "$report_path"
echo "Ended: $end_time" | tee -a "$report_path"
echo "Report saved to $report_path"
