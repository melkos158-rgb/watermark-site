#!/usr/bin/env pwsh
# tools/dev_audit_fix.ps1
# Automated dev audit and minimal auto-fix for Flask/Python projects (Windows PowerShell)
# Usage: .\tools\dev_audit_fix.ps1

param(
    [string]$ReportDir = "../reports"
)

$ErrorActionPreference = 'Stop'
$startTime = Get-Date
$timestamp = $startTime.ToString('yyyy-MM-dd_HHmm')
$reportPath = Join-Path $ReportDir "dev_audit_fix_$timestamp.txt"

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

Add-Content -Path $reportPath -Value "Dev Audit+Fix started: $startTime"

Write-Section "PYTHON VERSION"
$pyExe = (Get-Command python).Source
$pyVer = python --version 2>&1
Write-Sub "Python: $pyExe"
Write-Sub "Version: $pyVer"

Write-Section "PIP CHECK"
$pipCheck = python -m pip check 2>&1
$pipCheck | Add-Content -Path $reportPath
if ($pipCheck -match 'ERROR|not installed|failed') {
    Write-Host "CRITICAL: pip check failed." -ForegroundColor Red
    exit 3
}

function Fix-IndentationError {
    param($file, $line)
    Write-Host "Attempting to auto-fix indentation in $file at line $line..." -ForegroundColor Yellow
    python tools/dev_audit_fix.py --fix-indentation --file $file --line $line | Add-Content -Path $reportPath
}

$compileAttempts = 0
$maxCompileAttempts = 2
$compileSuccess = $false
while ($compileAttempts -le $maxCompileAttempts) {
    Write-Section "COMPILE: python -m compileall -q . (attempt $($compileAttempts+1))"
    $compile = python -m compileall -q . 2>&1
    $compile | Add-Content -Path $reportPath
    if ($LASTEXITCODE -eq 0) {
        $compileSuccess = $true
        break
    }
    $err = $compile | Select-String -Pattern 'File "(.+)", line (\d+)' | Select-Object -First 1
    if ($err) {
        $file = $err.Matches[0].Groups[1].Value
        $line = $err.Matches[0].Groups[2].Value
        Fix-IndentationError -file $file -line $line
    } else {
        Write-Host "CRITICAL: Compile failed. See report." -ForegroundColor Red
        exit 2
    }
    $compileAttempts++
}
if (-not $compileSuccess) {
    Write-Host "CRITICAL: Compile failed after $maxCompileAttempts attempts. See report for details." -ForegroundColor Red
    exit 2
}

Write-Section "FLASK ROUTES"
try {
    $flaskRoutes = python -m flask --app app routes 2>&1
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
        $dbCurrent = python -m flask --app app db current 2>&1
        $dbCurrent | Add-Content -Path $reportPath
        $dbCheck = python -m flask --app app db check 2>&1
        $dbCheck | Add-Content -Path $reportPath
    } else {
        Write-Host "Flask-Migrate not present, skipping." -ForegroundColor Yellow
        Add-Content -Path $reportPath -Value "Flask-Migrate not present, skipping."
    }
} catch {
    Write-Host "Flask-Migrate not present, skipping." -ForegroundColor Yellow
    Add-Content -Path $reportPath -Value "Flask-Migrate not present, skipping."
}

Write-Section "LINT/FIX: ruff, black, isort, autoflake"
foreach ($tool in @('ruff','black','isort','autoflake','pip-audit')) {
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

Write-Section "SECURITY: pip-audit"
$pipAuditOut = pip-audit 2>&1
$pipAuditOut | Add-Content -Path $reportPath
if ($pipAuditOut -match 'VULNERABLE|CRITICAL|HIGH') {
    Write-Host "CRITICAL: Vulnerabilities found by pip-audit!" -ForegroundColor Red
    exit 4
}

Write-Section "PYTEST"
if (Test-Path "test_followers_api.py" -or (Test-Path "tests" -and (Get-ChildItem tests -Filter *.py | Measure-Object).Count -gt 0)) {
    $pytest = python -m pip show pytest 2>&1
    if ($pytest -notmatch 'Name: pytest') {
        Write-Sub "Installing pytest..."
        python -m pip install pytest | Add-Content -Path $reportPath
    }
    $pytestOut = pytest -q 2>&1
    $pytestOut | Add-Content -Path $reportPath
    if ($pytestOut -match 'Connection refused.*localhost:5000') {
        Write-Host "Detected real server test. Attempting to auto-fix to Flask test client..." -ForegroundColor Yellow
        python tools/dev_audit_fix.py --fix-tests | Add-Content -Path $reportPath
        $pytestOut = pytest -q 2>&1
        $pytestOut | Add-Content -Path $reportPath
        if ($pytestOut -match 'FAILED') {
            Write-Host "CRITICAL: Tests still failing after auto-fix. See report." -ForegroundColor Red
            exit 6
        }
    } elseif ($pytestOut -match 'FAILED') {
        Write-Host "CRITICAL: Tests failed. See report." -ForegroundColor Red
        exit 6
    }
} else {
    Write-Sub "No tests found, skipping pytest."
}

$endTime = Get-Date
Add-Content -Path $reportPath -Value "`n==== DEV AUDIT+FIX COMPLETE ===="
Add-Content -Path $reportPath -Value "Started: $startTime"
Add-Content -Path $reportPath -Value "Ended: $endTime"
Write-Host "`n==== DEV AUDIT+FIX COMPLETE ====" -ForegroundColor Green
Write-Host "Report saved to $reportPath"
Write-Host "To run again: .\tools\dev_audit_fix.ps1"
