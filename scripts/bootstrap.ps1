Param(
    [string]$PythonVersion = "3.13"
)

$ErrorActionPreference = "Stop"

function Assert-LastExitCode([string]$StepName) {
    if ($LASTEXITCODE -ne 0) {
        throw "$StepName failed with exit code $LASTEXITCODE"
    }
}

Write-Host "Creating virtual environment (.venv) with Python $PythonVersion ..."
py -$PythonVersion -m venv .venv
Assert-LastExitCode "Virtual environment creation"

Write-Host "Installing dependencies ..."
.\.venv\Scripts\python -m pip install -r requirements\local.txt
Assert-LastExitCode "Dependencies installation"

if (!(Test-Path ".env")) {
    Write-Host "Creating .env from .env.example ..."
    Copy-Item .env.example .env
}

Write-Host "Starting infrastructure (PostgreSQL, Redis, MinIO) ..."
docker compose up -d
Assert-LastExitCode "Docker compose startup"

Write-Host "Running migrations ..."
.\.venv\Scripts\python manage.py migrate
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Migration failed. Most common reason: PostgreSQL with another password/old volume."
    Write-Host "Try reset DB container and volume:"
    Write-Host "  docker compose down -v"
    Write-Host "  docker compose up -d"
    throw "Database migration failed"
}

Write-Host "Bootstrap complete."
Write-Host "Run app: .\.venv\Scripts\python manage.py runserver"
