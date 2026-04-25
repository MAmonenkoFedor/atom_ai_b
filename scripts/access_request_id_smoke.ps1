param(
    [string]$BaseUrl = "http://127.0.0.1:8765",
    [string]$Username = "super_admin_test",
    [string]$Password = "AtomTest123!"
)

$ErrorActionPreference = "Stop"

$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession

Write-Host "[1] csrf"
$null = Invoke-WebRequest -Uri "$BaseUrl/api/v1/auth/csrf" -WebSession $session -UseBasicParsing
$csrf = ($session.Cookies.GetCookies($BaseUrl) | Where-Object { $_.Name -eq "csrftoken" }).Value

Write-Host "[2] login"
$null = Invoke-WebRequest -Uri "$BaseUrl/api/v1/auth/login" -Method Post -Body (@{ username = $Username; password = $Password } | ConvertTo-Json) -ContentType "application/json" -Headers @{ "X-CSRFToken" = $csrf; "Referer" = $BaseUrl } -WebSession $session -UseBasicParsing
$csrf = ($session.Cookies.GetCookies($BaseUrl) | Where-Object { $_.Name -eq "csrftoken" }).Value

Write-Host "[3] resolve employee_test"
$users = Invoke-RestMethod -Uri "$BaseUrl/api/v1/super-admin/users?search=employee_test" -WebSession $session
$arr = if ($users.items) { $users.items } elseif ($users.results) { $users.results } else { $users }
$emp = $arr | Where-Object { $_.username -eq "employee_test" } | Select-Object -First 1
$empId = $emp.id

$traceId = "smoke-trace-$([Guid]::NewGuid().ToString('N').Substring(0,12))"
Write-Host "[4] POST grants with X-Request-Id=$traceId"
$body = @{ employee_id = $empId; permission_code = "docs.view"; scope_type = "project"; scope_id = "arena"; grant_mode = "use_only"; note = "rid-smoke" } | ConvertTo-Json
$resp = Invoke-WebRequest -Uri "$BaseUrl/api/v1/access/grants" -Method Post -Body $body -ContentType "application/json" -Headers @{ "X-CSRFToken" = $csrf; "Referer" = $BaseUrl; "X-Request-Id" = $traceId } -WebSession $session -UseBasicParsing
$grant = $resp.Content | ConvertFrom-Json
$echoed = $resp.Headers["X-Request-Id"]
Write-Host "    grant id=$($grant.id) echoed=$echoed"
if ($echoed -ne $traceId) { throw "X-Request-Id echo mismatch: '$echoed' != '$traceId'" }

Write-Host "[5] check audit log entry has request_id=$traceId"
$audit = Invoke-RestMethod -Uri "$BaseUrl/api/v1/access/employees/$empId/audit?limit=10" -WebSession $session
$rows = if ($audit.items) { $audit.items } else { $audit }
$last = $rows | Where-Object { $_.note -eq "rid-smoke" -or $_.action -eq "grant_created" } | Select-Object -First 1
if (-not $last) { throw "no audit entry found" }
Write-Host "    audit row: action=$($last.action) request_id=$($last.request_id) actor=$($last.actor_email)"
if ($last.request_id -ne $traceId) { throw "request_id not propagated to audit: '$($last.request_id)' != '$traceId'" }

Write-Host "[6] cleanup: revoke grant"
$null = Invoke-WebRequest -Uri "$BaseUrl/api/v1/access/grants/$($grant.id)/revoke" -Method Post -Body (@{ note = "rid-smoke-revoke" } | ConvertTo-Json) -ContentType "application/json" -Headers @{ "X-CSRFToken" = $csrf; "Referer" = $BaseUrl } -WebSession $session -UseBasicParsing

Write-Host "=== request-id smoke OK ==="
