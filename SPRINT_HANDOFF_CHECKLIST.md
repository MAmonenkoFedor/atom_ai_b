# Sprint Handoff Checklist (Live Smoke)

Date: 2026-04-15
Environment: `http://127.0.0.1:8000/api`
Scope source: `API_BACKEND_PARALLEL_REQUESTS_v2.md`

## 1) Auth + Session

| Endpoint | Method | Status | Notes |
|---|---|---|---|
| `/api/auth/login` | POST | 200 | `company_admin_test` and `super_admin_test` login OK |
| `/api/auth/session` | GET | 200 | Session payload returned |
| `/api/auth/logout` | POST | Not re-run in this smoke | Endpoint exists and documented in schema |
| `/api/auth/invite/activate` | POST | Not re-run in this smoke | Endpoint exists and documented in schema |

## 2) Buildings / Workspace / Profile

| Endpoint | Method | Status | Notes |
|---|---|---|---|
| `/api/buildings` | GET | 200 | |
| `/api/buildings/{building_id}` | GET | 200 | Tested with `building_id=bcs-drift` |
| `/api/buildings/{building_id}/departments` | GET | 200 | |
| `/api/buildings/{building_id}/floors/{floor_id}/workspace` | GET | 200 | Tested with `floor_id=3` |
| `/api/buildings/{building_id}/floors/{floor_id}/workspace/employee/{employee_id}` | GET | 200 | Tested with `employee_id=emp-1` |
| `/api/buildings/{building_id}/floors/{floor_id}/employees/{employee_id}/profile` | GET | 200 | |
| `/api/buildings/{building_id}/floors/{floor_id}/workspace-context?employee_id=` | GET | 200 | Alias OK |
| `/api/workspace/context?...` | GET | 200 | Alias OK |
| `/api/employees/{employee_id}/profile?...` | GET | 200 | Alias OK |

## 3) Projects

| Endpoint | Method | Status | Notes |
|---|---|---|---|
| `/api/projects` | GET | 200 | List and filters (`q`, `status`) OK |
| `/api/projects/{project_id}` | GET | 200 | |
| `/api/projects` | POST | 201 | |
| `/api/projects/{project_id}` | PATCH | 200 | |
| `/api/projects/{project_id}/archive` | POST | 200 | |
| `/api/projects/{project_id}/restore` | POST | 200 | |
| `/api/projects/{project_id}/members` | GET | 200 | |
| `/api/projects/{project_id}/members` | POST | 201 | |
| `/api/projects/{project_id}/members/{member_id}` | PATCH | 200 | |
| `/api/projects/{project_id}/members/{member_id}` | DELETE | 204 | |

## 4) Company Admin (Primary + Alias)

| Endpoint | Method | Status | Notes |
|---|---|---|---|
| `/api/company/admin/overview` | GET | 200 | |
| `/api/company/admin/departments` | GET | 200 | |
| `/api/company/admin/users` | GET | 200 | filter `q` tested |
| `/api/company/admin/invites` | GET | 200 | |
| `/api/company/admin/invites` | POST | 201 | |
| `/api/company/admin/users/{user_id}/role` | PATCH | 200 | |
| `/api/company/admin/invites/{invite_id}/revoke` | POST | 200 | |
| `/api/admin/company/*` | GET/PATCH/POST | 200/201 | Alias endpoints tested OK |

## 5) Super Admin + Platform Audit + Action Center

| Endpoint | Method | Status | Notes |
|---|---|---|---|
| `/api/admin/platform/overview` | GET | 200 | |
| `/api/admin/platform/tenants` | GET | 200 | |
| `/api/admin/platform/users` | GET | 200 | |
| `/api/admin/platform/invites` | GET | 200 | |
| `/api/admin/platform/tenants` | POST | 201 | |
| `/api/admin/platform/tenants/{tenant_id}/status` | PATCH | 200 | |
| `/api/admin/platform/invites` | POST | 201 | |
| `/api/admin/platform/invites/{invite_id}/revoke` | POST | 200 | |
| `/api/admin/platform/audit/stats` | GET | 200 | |
| `/api/admin/platform/audit/events` | GET | 200 | Page + cursor mode tested |
| `/api/admin/platform/audit/export` | GET | 200 | `Content-Type: text/csv` |
| `/api/admin/actions/stats` | GET | 200 | |
| `/api/admin/actions/events` | GET | 200 | Page + cursor mode tested |
| `/api/admin/actions/events/{action_id}` | GET | Covered earlier | Endpoint exists and documented |
| `/api/platform/admin/*` | GET | 200 | Alias endpoints tested OK |

## 6) Contract/Schema Status

- Alignment schema includes auth/workspace/projects/company/super-admin/audit/action/tasks paths.
- `spectacular --validate --urlconf config.alignment_schema_urls`: errors `0`, warnings `0`.
- Error contract for frontend-critical paths is DRF style `{ "detail": "..." }`.

## 7) Important Operational Note

- For session-based auth in live smoke, unsafe methods (`POST/PATCH/DELETE`) require CSRF header:
  - cookie: `csrftoken`
  - header: `X-CSRFToken`
- Without this header, backend correctly returns `403 CSRF token missing`.
