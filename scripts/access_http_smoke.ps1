param(
    [string]$BaseUrl = "http://127.0.0.1:8765",
    [string]$Username = "super_admin_test",
    [string]$Password = "AtomTest123!"
)

$ErrorActionPreference = "Stop"

function Invoke-Json {
    param(
        [string]$Method,
        [string]$Url,
        [object]$Body = $null,
        [System.Net.CookieContainer]$Cookies,
        [hashtable]$Extra = @{}
    )
    $params = @{
        Uri = $Url
        Method = $Method
        WebSession = $script:Session
        ContentType = "application/json"
    }
    if ($Body) {
        $params.Body = ($Body | ConvertTo-Json -Depth 8 -Compress)
    }
    foreach ($k in $Extra.Keys) {
        $params[$k] = $Extra[$k]
    }
    Invoke-RestMethod @params
}

$script:Session = New-Object Microsoft.PowerShell.Commands.WebRequestSession

Write-Host "[1] csrf"
$null = Invoke-RestMethod -Uri "$BaseUrl/api/v1/auth/csrf" -WebSession $script:Session
$csrf = ($script:Session.Cookies.GetCookies($BaseUrl) | Where-Object { $_.Name -eq "csrftoken" }).Value
if (-not $csrf) { throw "no csrftoken" }
Write-Host "    csrf=$($csrf.Substring(0,8))..."

Write-Host "[2] login as $Username"
$loginHeaders = @{ "X-CSRFToken" = $csrf; "Referer" = $BaseUrl }
$null = Invoke-RestMethod -Uri "$BaseUrl/api/v1/auth/login" -Method Post -Body (@{ username = $Username; password = $Password } | ConvertTo-Json) -ContentType "application/json" -Headers $loginHeaders -WebSession $script:Session
Write-Host "    login OK"

# Refresh CSRF cookie value (Django rotates after login)
$csrf = ($script:Session.Cookies.GetCookies($BaseUrl) | Where-Object { $_.Name -eq "csrftoken" }).Value
$mutHeaders = @{ "X-CSRFToken" = $csrf; "Referer" = $BaseUrl }

Write-Host "[3] GET /api/v1/access/permissions"
$cat = Invoke-RestMethod -Uri "$BaseUrl/api/v1/access/permissions" -WebSession $script:Session
Write-Host "    items: $($cat.items.Count) total=$($cat.total)"

Write-Host "[4] GET /api/v1/access/role-templates"
$tpls = Invoke-RestMethod -Uri "$BaseUrl/api/v1/access/role-templates" -WebSession $script:Session
Write-Host "    templates: $($tpls.items.Count) total=$($tpls.total)"

Write-Host "[5] GET /api/v1/access/delegation-rules"
$rules = Invoke-RestMethod -Uri "$BaseUrl/api/v1/access/delegation-rules" -WebSession $script:Session
Write-Host "    delegation rules: $($rules.items.Count) total=$($rules.total)"

Write-Host "[6] resolve employee_test user id via /api/v1/super-admin/users"
$users = Invoke-RestMethod -Uri "$BaseUrl/api/v1/super-admin/users?search=employee_test" -WebSession $script:Session
$arr = if ($users.items) { $users.items } elseif ($users.results) { $users.results } else { $users }
$emp = $arr | Where-Object { $_.username -eq "employee_test" } | Select-Object -First 1
if (-not $emp) { throw "cannot find employee_test in admin users; payload=$(ConvertTo-Json $users -Depth 4 -Compress)" }
$empId = $emp.id
Write-Host "    employee_test id=$empId"

Write-Host "[7] POST /api/v1/access/grants - grant docs.upload @ project:arena (use_only)"
$grantBody = @{
    employee_id = $empId
    permission_code = "docs.upload"
    scope_type = "project"
    scope_id = "arena"
    grant_mode = "use_only"
    note = "http-smoke"
}
$grant = Invoke-Json -Method Post -Url "$BaseUrl/api/v1/access/grants" -Body $grantBody -Extra @{ Headers = $mutHeaders }
Write-Host "    grant id=$($grant.id) status=$($grant.status)"

Write-Host "[8] GET /api/v1/access/employees/$empId/effective-permissions"
$eff = Invoke-RestMethod -Uri "$BaseUrl/api/v1/access/employees/$empId/effective-permissions" -WebSession $script:Session
$count = if ($eff.permissions) { $eff.permissions.Count } elseif ($eff.items) { $eff.items.Count } else { $eff.Count }
Write-Host "    effective count=$count"

Write-Host "[9] POST /api/v1/access/grants/$($grant.id)/revoke"
$revoked = Invoke-Json -Method Post -Url "$BaseUrl/api/v1/access/grants/$($grant.id)/revoke" -Body @{ note = "http-smoke-revoke" } -Extra @{ Headers = $mutHeaders }
Write-Host "    status=$($revoked.status)"

Write-Host "[10] GET /api/v1/access/employees/$empId/audit"
$audit = Invoke-RestMethod -Uri "$BaseUrl/api/v1/access/employees/$empId/audit?limit=5" -WebSession $script:Session
$auditCount = if ($audit.items) { $audit.items.Count } elseif ($audit.results) { $audit.results.Count } else { $audit.Count }
Write-Host "    audit entries (last 5): $auditCount"

Write-Host "=== HTTP SMOKE OK ==="
