param(
    [string]$BaseUrl = "http://127.0.0.1:8765/api",
    [ValidateSet("Fast", "Full")]
    [string]$Mode = "Full",
    [string]$SmokeJsonReportPath = ".\smoke_report.json"
)

$ErrorActionPreference = "Stop"
$PythonBin = ".\.venv\Scripts\python.exe"

if (-not (Test-Path $PythonBin)) {
    throw "Python virtual environment not found at $PythonBin. Create/activate .venv before running audit_gate.ps1."
}

function Run-Step {
    param(
        [string]$Name,
        [scriptblock]$Action
    )
    Write-Host ""
    Write-Host "== $Name ==" -ForegroundColor Cyan
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "Step failed: $Name (exit code $LASTEXITCODE)"
    }
}

Run-Step -Name "Django checks" -Action {
    & $PythonBin manage.py check
}

Run-Step -Name "Seed access catalog" -Action {
    & $PythonBin manage.py seed_access_control
}

Run-Step -Name "Access privacy defaults check" -Action {
    & $PythonBin manage.py check_access_privacy_defaults
}

Run-Step -Name "Alignment schema validate" -Action {
    & $PythonBin manage.py spectacular --validate --file alignment_openapi.yaml --urlconf config.alignment_schema_urls
}

Run-Step -Name "Smoke runner" -Action {
    .\SMOKE_RUNNER.ps1 -BaseUrl $BaseUrl -Mode $Mode -JsonReportPath $SmokeJsonReportPath
}

Write-Host ""
Write-Host "Audit gate passed." -ForegroundColor Green
Write-Host "Smoke report: $SmokeJsonReportPath" -ForegroundColor Green
