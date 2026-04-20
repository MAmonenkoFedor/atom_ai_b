# ATOM AI Backend (Phase 0 Bootstrap)

Production-ready backend foundation for ATOM AI Workspace:

- Django + DRF
- PostgreSQL + Redis + Celery
- MinIO (S3-compatible)
- OpenAPI via drf-spectacular
- Unified error + pagination formats
- Health checks (`/health/live`, `/health/ready`)

## 1) Local setup

Fast path:

```powershell
cd d:\ATOM_AI_backend
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1
```

Manual path:

```powershell
cd d:\ATOM_AI_backend
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements\local.txt
copy .env.example .env
docker compose up -d
python manage.py migrate
python manage.py runserver
```

PostgreSQL is mapped to host port `5433` by default to avoid conflicts with local DB instances.

If migration fails due old DB password/volume, reset containers:

```powershell
docker compose down -v
docker compose up -d
python manage.py migrate
```

## 2) Celery

```powershell
cd d:\ATOM_AI_backend
.\.venv\Scripts\Activate.ps1
celery -A config worker -l info
```

## 3) API endpoints

- App API root: `http://127.0.0.1:8000/api/v1/`
- OpenAPI schema: `http://127.0.0.1:8000/api/schema/`
- Swagger: `http://127.0.0.1:8000/api/docs/`
- Liveness: `http://127.0.0.1:8000/health/live/`
- Readiness: `http://127.0.0.1:8000/health/ready/`

## 4) Settings profiles

- local: `config.settings.local`
- stage: `config.settings.stage`
- prod: `config.settings.prod`

## 5) LLM gateway mode

- Default mode is `mock` (`LLM_GATEWAY_MOCK_MODE=True`) for safe local bootstrap.
- For real provider calls set:
  - `LLM_GATEWAY_MOCK_MODE=False`
  - `OPENAI_API_KEY` (for OpenAI)
  - `ANTHROPIC_API_KEY` (for Claude)
  - `GEMINI_API_KEY` (for Gemini)
- Optional tuning:
  - `LLM_GATEWAY_TIMEOUT_MS`
  - `LLM_GATEWAY_MAX_RETRIES`
  - `LLM_GATEWAY_ENABLE_FALLBACK`

## 6) Frontend live integration

- Frontend live connection guide:
  - `FRONTEND_LIVE_CONNECTION_GUIDE.md`
- Canonical backend contract:
  - `BACKEND_HANDOFF.md`
- Employee vertical packet:
  - `EMPLOYEE_BACKEND_PACKET.md`
