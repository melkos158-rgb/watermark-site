#!/usr/bin/env pwsh
# tools/top1_audit.ps1
# Top-1 Quality Terminal Audit for Flask/Python projects (Windows PowerShell)
# Usage: .\tools\top1_audit.ps1

param(
    [string]$ReportDir = "../reports"
)

$ErrorActionPreference = 'Stop'
$startTime = Get-Date
$timestamp = $startTime.ToString('yyyy-MM-dd_HHmm')
$reportPath = Join-Path $ReportDir "top1_audit_$timestamp.txt"

function Write-Section($title) {
    Write-Host "`n==== $title ====" -ForegroundColor Cyan
    Add-Content -Path $reportPath -Value "`n==== $title ===="
}

function Write-Sub($msg) {
    Write-Host "-- $msg" -ForegroundColor DarkGray
    Add-Content -Path $reportPath -Value "-- $msg"
}

# Ensure report dir exists
if (-not (Test-Path $ReportDir)) { New-Item -ItemType Directory -Path $ReportDir | Out-Null }

Add-Content -Path $reportPath -Value "Top-1 Audit started: $startTime"

Write-Section "VENV CHECK"
if (-not $env:VIRTUAL_ENV) {
    Write-Host "WARNING: Python venv is not active! Activate your venv before running the audit." -ForegroundColor Yellow
    Add-Content -Path $reportPath -Value "WARNING: Python venv is not active! Activate your venv before running the audit."
}
else {
    Write-Sub "Venv: $env:VIRTUAL_ENV"
}

Write-Section "PYTHON VERSION"
$pyExe = (Get-Command python).Source
$pyVer = python --version 2>&1
Write-Sub "Python: $pyExe"
Write-Sub "Version: $pyVer"

Write-Section "COMPILE: python -m compileall -q ."
$compile = python -m compileall -q . 2>&1
if ($LASTEXITCODE -ne 0) {
    $err = $compile | Select-String -Pattern 'File "(.+)", line (\d+)' | Select-Object -First 1
    if ($err) {
        Write-Host "CRITICAL: Indentation/Syntax error in $($err.Matches[0].Groups[1].Value) at line $($err.Matches[0].Groups[2].Value)" -ForegroundColor Red
        Add-Content -Path $reportPath -Value "CRITICAL: Indentation/Syntax error in $($err.Matches[0].Groups[1].Value) at line $($err.Matches[0].Groups[2].Value)"
        Write-Host "Please fix indentation (convert tabs to 4 spaces) and re-run."
        exit 2
    } else {
        Write-Host "CRITICAL: Compile failed. See report."
        Add-Content -Path $reportPath -Value "CRITICAL: Compile failed."
        $compile | Add-Content -Path $reportPath
        exit 2
    }
}
$compile | Add-Content -Path $reportPath

Write-Section "PIP CHECK"
$pipCheck = python -m pip check 2>&1
$pipCheck | Add-Content -Path $reportPath
if ($pipCheck -match 'ERROR|not installed|failed') {
    Write-Host "CRITICAL: pip check failed." -ForegroundColor Red
    exit 3
}

Write-Section "PIP OUTDATED"
$pipOut = python -m pip list --outdated 2>&1
$pipOut | Add-Content -Path $reportPath

Write-Section "FLASK ROUTES"
$flaskApp = 'app'
try {
    $flaskRoutes = python -m flask --app $flaskApp routes 2>&1
    $flaskRoutes | Add-Content -Path $reportPath
    if ($flaskRoutes -match 'Error:') {
        Write-Host "Flask app import failed, skipping routes." -ForegroundColor Yellow
        Add-Content -Path $reportPath -Value "Flask app import failed, skipping routes."
    }
} catch {
    Write-Host "Flask not available or app import failed, skipping routes." -ForegroundColor Yellow
    Add-Content -Path $reportPath -Value "Flask not available or app import failed, skipping routes."
}

Write-Section "FLASK-MIGRATE"
try {
    $hasMigrate = python -c "import flask_migrate" 2>&1
    if ($LASTEXITCODE -eq 0) {
        $dbCurrent = python -m flask --app $flaskApp db current 2>&1
        $dbCurrent | Add-Content -Path $reportPath
        $dbCheck = python -m flask --app $flaskApp db check 2>&1
        $dbCheck | Add-Content -Path $reportPath
    } else {
        Write-Host "Flask-Migrate not present, skipping." -ForegroundColor Yellow
        Add-Content -Path $reportPath -Value "Flask-Migrate not present, skipping."
    }
} catch {
    Write-Host "Flask-Migrate not present, skipping." -ForegroundColor Yellow
    Add-Content -Path $reportPath -Value "Flask-Migrate not present, skipping."
}

Write-Section "SECURITY: pip-audit"
$pipAudit = python -m pip show pip-audit 2>&1
if ($pipAudit -notmatch 'Name: pip-audit') {
    Write-Sub "Installing pip-audit..."
    python -m pip install pip-audit | Add-Content -Path $reportPath
}
$pipAuditOut = pip-audit 2>&1
$pipAuditOut | Add-Content -Path $reportPath
if ($pipAuditOut -match 'VULNERABLE|CRITICAL|HIGH') {
    Write-Host "CRITICAL: Vulnerabilities found by pip-audit!" -ForegroundColor Red
    exit 4
}

Write-Section "LINT/FIX: ruff, black, isort, autoflake"
foreach ($tool in @('ruff','black','isort','autoflake')) {
    $toolCheck = python -m pip show $tool 2>&1
    if ($toolCheck -notmatch "Name: $tool") {
        Write-Sub "Installing $tool..."
        python -m pip install $tool | Add-Content -Path $reportPath
    }
}
ruff check . --fix 2>&1 | Add-Content -Path $reportPath
black . 2>&1 | Add-Content -Path $reportPath
isort . 2>&1 | Add-Content -Path $reportPath
autoflake --in-place --recursive --remove-all-unused-imports --remove-unused-variables . 2>&1 | Add-Content -Path $reportPath

Write-Section "RE-COMPILE AFTER FIXES"
$recompile = python -m compileall -q . 2>&1
$recompile | Add-Content -Path $reportPath
if ($LASTEXITCODE -ne 0) {
    Write-Host "CRITICAL: Compile failed after auto-fixes. See report." -ForegroundColor Red
    exit 5
}

Write-Section "OPTIONAL: MYPY TYPE CHECK"
if (Test-Path "mypy.ini" -or Test-Path "pyproject.toml") {
    $mypyCheck = python -m pip show mypy 2>&1
    if ($mypyCheck -notmatch 'Name: mypy') {
        Write-Sub "Installing mypy..."
        python -m pip install mypy | Add-Content -Path $reportPath
    }
    mypy . 2>&1 | Add-Content -Path $reportPath
} else {
    Write-Sub "No mypy config found, skipping type check."
}

$endTime = Get-Date
Add-Content -Path $reportPath -Value "`n==== AUDIT COMPLETE ===="
Add-Content -Path $reportPath -Value "Started: $startTime"
Add-Content -Path $reportPath -Value "Ended: $endTime"
Write-Host "`n==== AUDIT COMPLETE ====" -ForegroundColor Green
Write-Host "Report saved to $reportPath"
