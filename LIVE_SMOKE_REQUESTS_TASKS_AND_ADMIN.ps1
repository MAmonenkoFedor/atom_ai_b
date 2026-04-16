$BASE = "http://127.0.0.1:8000/api"

Write-Host "== LOGIN (company_admin) =="
curl.exe -s -c company.cookie -H "Content-Type: application/json" `
  -d "{\"username\":\"company_admin_test\",\"password\":\"Pass12345!\"}" `
  "$BASE/auth/login"
Write-Host ""

Write-Host "== TASKS LIST =="
curl.exe -s -b company.cookie "$BASE/tasks"
Write-Host ""

Write-Host "== TASKS FILTERED (status=in_progress) =="
curl.exe -s -b company.cookie "$BASE/tasks?status=in_progress"
Write-Host ""

Write-Host "== TASKS PAGED+SORTED (sort=-created_at,page=1,page_size=2) =="
curl.exe -s -b company.cookie "$BASE/tasks?sort=-created_at&page=1&page_size=2"
Write-Host ""

Write-Host "== TASKS INCREMENTAL (updated_at_from) =="
curl.exe -s -b company.cookie "$BASE/tasks?updated_at_from=2026-04-15T00:00:00Z&sort=-updated_at&page=1&page_size=5"
Write-Host ""

Write-Host "== TASKS CURSOR PAGE 1 (page_size=2) =="
$cursorPage1 = curl.exe -s -b company.cookie "$BASE/tasks?cursor=&page_size=2"
$cursorPage1
Write-Host ""

Write-Host "== TASKS CURSOR PAGE 2 (use next_cursor from page 1 manually if needed) =="
# Example:
# curl.exe -s -b company.cookie "$BASE/tasks?cursor=2026-04-15T12:00:00Z::2003&page_size=2"
Write-Host ""

Write-Host "== TASK CREATE =="
curl.exe -s -b company.cookie -H "Content-Type: application/json" `
  -d "{\"title\":\"Smoke task from script\",\"description\":\"created via ps1\",\"status\":\"todo\",\"priority\":\"high\",\"project_id\":1,\"assignee_id\":12,\"department_id\":1}" `
  "$BASE/tasks"
Write-Host ""

Write-Host "== TASKS STATS =="
curl.exe -s -b company.cookie "$BASE/tasks/stats"
Write-Host ""

Write-Host "== TASKS BOARD =="
curl.exe -s -b company.cookie "$BASE/tasks/board"
Write-Host ""

Write-Host "== TASK DETAIL (id=2001) =="
curl.exe -s -b company.cookie "$BASE/tasks/2001"
Write-Host ""

Write-Host "== TASK DELETE (id=2002) =="
curl.exe -s -i -b company.cookie -X DELETE "$BASE/tasks/2002"
Write-Host ""

Write-Host "== TASK BULK STATUS (ids=2001,2003 -> done) =="
curl.exe -s -b company.cookie -X PATCH -H "Content-Type: application/json" `
  -d "{\"task_ids\":[2001,2003],\"status\":\"done\"}" `
  "$BASE/tasks/bulk/status"
Write-Host ""

Write-Host "== TASK BULK ASSIGN (ids=2001,2003 -> assignee_id=11) =="
curl.exe -s -b company.cookie -X PATCH -H "Content-Type: application/json" `
  -d "{\"task_ids\":[2001,2003],\"assignee_id\":11}" `
  "$BASE/tasks/bulk/assign"
Write-Host ""

Write-Host "== TASK ACTIVITY (id=2001) =="
curl.exe -s -b company.cookie "$BASE/tasks/2001/activity"
Write-Host ""

Write-Host "== TASK ACTIVITY PAGED+SORTED (id=2001) =="
curl.exe -s -b company.cookie "$BASE/tasks/2001/activity?sort=-created_at&page=1&page_size=5"
Write-Host ""

Write-Host "== TASK ACTIVITY CURSOR PAGE 1 (id=2001,page_size=2) =="
$activityCursorPage1 = curl.exe -s -b company.cookie "$BASE/tasks/2001/activity?cursor=&page_size=2"
$activityCursorPage1
Write-Host ""

Write-Host "== COMPANY ADMIN OVERVIEW =="
curl.exe -s -b company.cookie "$BASE/company/admin/overview"
Write-Host ""

Write-Host "== LOGIN (super_admin) =="
curl.exe -s -c super.cookie -H "Content-Type: application/json" `
  -d "{\"username\":\"super_admin_test\",\"password\":\"Pass12345!\"}" `
  "$BASE/auth/login"
Write-Host ""

Write-Host "== SUPER ADMIN OVERVIEW =="
curl.exe -s -b super.cookie "$BASE/admin/platform/overview"
Write-Host ""

Write-Host "== AUDIT EVENTS =="
curl.exe -s -b super.cookie "$BASE/admin/platform/audit/events?page=1&page_size=5"
Write-Host ""

Write-Host "== AUDIT EVENTS CURSOR PAGE 1 =="
$auditCursorPage1 = curl.exe -s -b super.cookie "$BASE/admin/platform/audit/events?cursor=&page_size=2"
$auditCursorPage1
Write-Host ""

Write-Host "== ACTION CENTER EVENTS =="
curl.exe -s -b super.cookie "$BASE/admin/actions/events?page=1&page_size=5"
Write-Host ""

Write-Host "== ACTION CENTER CURSOR PAGE 1 =="
$actionCursorPage1 = curl.exe -s -b super.cookie "$BASE/admin/actions/events?cursor=&page_size=2"
$actionCursorPage1
Write-Host ""
