param(
    [string]$BaseUrl = "http://127.0.0.1:8000/api",
    [ValidateSet("Fast", "Full")]
    [string]$Mode = "Full",
    [string]$SmokeJsonReportPath = ".\smoke_report.json"
)

$ErrorActionPreference = "Stop"

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
    .\.venv\Scripts\python.exe manage.py check
}

Run-Step -Name "Alignment schema validate" -Action {
    .\.venv\Scripts\python.exe manage.py spectacular --validate --file alignment_openapi.yaml --urlconf config.alignment_schema_urls
}

Run-Step -Name "Smoke runner" -Action {
    .\SMOKE_RUNNER.ps1 -BaseUrl $BaseUrl -Mode $Mode -JsonReportPath $SmokeJsonReportPath
}

Write-Host ""
Write-Host "Audit gate passed." -ForegroundColor Green
Write-Host "Smoke report: $SmokeJsonReportPath" -ForegroundColor Green
