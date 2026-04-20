param(
    [string]$BaseUrl = "http://127.0.0.1:8000/api",
    [string]$CompanyUsername = "company_admin_test",
    [string]$EmployeeUsername = "employee_test",
    [string]$SuperUsername = "super_admin_test",
    [string]$Password = "Pass12345!",
    [ValidateSet("Fast", "Full")]
    [string]$Mode = "Full",
    [string]$JsonReportPath = "",
    [int]$StartupTimeoutSec = 20
)

$ErrorActionPreference = "Stop"

$script:Results = @()
$abort = $false

function Test-ApiUp {
    param([string]$ApiBaseUrl)
    $client = $null
    try {
        $uri = [System.Uri]$ApiBaseUrl
        $hostName = $uri.Host
        $port = $uri.Port
        if ($port -le 0) { $port = 80 }
        $client = New-Object System.Net.Sockets.TcpClient
        $asyncResult = $client.BeginConnect($hostName, $port, $null, $null)
        $connectedInTime = $asyncResult.AsyncWaitHandle.WaitOne(1500, $false)
        if (-not $connectedInTime) {
            return $false
        }
        $client.EndConnect($asyncResult)
        return $client.Connected
    } catch {
        return $false
    } finally {
        if ($null -ne $client) {
            $client.Close()
        }
    }
}

function Add-Result {
    param(
        [string]$Step,
        [string]$Method,
        [string]$Path,
        [string]$Expected,
        [int]$Actual,
        [bool]$Ok,
        [string]$Note = ""
    )
    $script:Results += [pscustomobject]@{
        step     = $Step
        method   = $Method
        path     = $Path
        expected = $Expected
        actual   = $Actual
        ok       = $Ok
        note     = $Note
    }
}

Write-Host "Preflight: waiting for API availability (timeout ${StartupTimeoutSec}s)..." -ForegroundColor DarkCyan
$apiUp = $false
$deadline = (Get-Date).AddSeconds($StartupTimeoutSec)
while ((Get-Date) -lt $deadline) {
    if (Test-ApiUp -ApiBaseUrl $BaseUrl) {
        $apiUp = $true
        break
    }
    Start-Sleep -Seconds 2
}

if (-not $apiUp) {
    Write-Host "API is not reachable: $BaseUrl" -ForegroundColor Red
    Write-Host "Hint: start backend (or docker) so host/port is listening, then re-run SMOKE_RUNNER.ps1" -ForegroundColor Yellow
    Add-Result -Step "preflight_api_up" -Method "TCP" -Path $BaseUrl -Expected "listening" -Actual 0 -Ok $false -Note "port closed/unreachable; timeout=${StartupTimeoutSec}s"
    $summary = [pscustomobject]@{
        mode = $Mode
        base_url = $BaseUrl
        generated_at = (Get-Date).ToString("o")
        total_checks = $script:Results.Count
        failed_checks = 1
        results = $script:Results
    }
    if (-not [string]::IsNullOrWhiteSpace($JsonReportPath)) {
        $reportDir = Split-Path -Path $JsonReportPath -Parent
        if (-not [string]::IsNullOrWhiteSpace($reportDir) -and -not (Test-Path -Path $reportDir)) {
            New-Item -ItemType Directory -Path $reportDir -Force | Out-Null
        }
        $summary | ConvertTo-Json -Depth 8 | Set-Content -Path $JsonReportPath -Encoding UTF8
        Write-Host "JSON report written to: $JsonReportPath" -ForegroundColor Cyan
    }
    exit 1
}

function Get-StatusCodeFromException {
    param($Exception)
    if ($null -eq $Exception -or $null -eq $Exception.Response) {
        return 0
    }
    try {
        return [int]$Exception.Response.StatusCode.value__
    } catch {
        return 0
    }
}

function Parse-JsonSafe {
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) {
        return $null
    }
    try {
        return $Text | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Get-ItemsFromListPayload {
    param($Payload)
    if ($null -eq $Payload) {
        return @()
    }
    if ($Payload -is [System.Array]) {
        return $Payload
    }
    if ($Payload.PSObject.Properties.Name -contains "results") {
        return @($Payload.results)
    }
    return @()
}

function Get-CsrfToken {
    param([Microsoft.PowerShell.Commands.WebRequestSession]$Session, [string]$Origin)
    try {
        $uri = [System.Uri]$Origin
        $cookie = $Session.Cookies.GetCookies($uri)["csrftoken"]
        if ($null -ne $cookie) {
            return [string]$cookie.Value
        }
    } catch {
    }
    return $null
}

function Invoke-Api {
    param(
        [string]$Step,
        [string]$Method,
        [string]$Path,
        [int[]]$ExpectedStatuses,
        [Microsoft.PowerShell.Commands.WebRequestSession]$Session,
        $Body = $null,
        [switch]$UseCsrf,
        [switch]$Silent
    )

    $uri = "$BaseUrl$Path"
    $headers = @{}
    $payload = $null
    if ($null -ne $Body) {
        $payload = $Body | ConvertTo-Json -Depth 8 -Compress
        $headers["Content-Type"] = "application/json"
    }
    if ($UseCsrf.IsPresent -and $Method -in @("POST", "PATCH", "PUT", "DELETE")) {
        $csrf = Get-CsrfToken -Session $Session -Origin $BaseUrl
        if (-not [string]::IsNullOrWhiteSpace($csrf)) {
            $headers["X-CSRFToken"] = $csrf
            $headers["Referer"] = "http://127.0.0.1:8000/"
        }
    }

    $statusCode = 0
    $content = ""
    $responseHeaders = @{}
    try {
        $resp = Invoke-WebRequest `
            -Uri $uri `
            -Method $Method `
            -WebSession $Session `
            -Headers $headers `
            -Body $payload `
            -UseBasicParsing `
            -TimeoutSec 30
        $statusCode = [int]$resp.StatusCode
        $content = [string]$resp.Content
        $responseHeaders = $resp.Headers
    } catch {
        $statusCode = Get-StatusCodeFromException -Exception $_.Exception
        try {
            $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
            $content = $reader.ReadToEnd()
        } catch {
            $content = $_.Exception.Message
        }
    }

    $ok = $ExpectedStatuses -contains $statusCode
    Add-Result `
        -Step $Step `
        -Method $Method `
        -Path $Path `
        -Expected (($ExpectedStatuses -join "/")) `
        -Actual $statusCode `
        -Ok $ok `
        -Note ""

    if (-not $Silent.IsPresent -and -not $ok) {
        Write-Host "FAILED [$Step] $Method $Path -> $statusCode (expected $($ExpectedStatuses -join '/'))" -ForegroundColor Red
        if (-not [string]::IsNullOrWhiteSpace($content)) {
            Write-Host $content
        }
    }

    return [pscustomobject]@{
        StatusCode = $statusCode
        Content = $content
        Headers = $responseHeaders
        Ok = $ok
    }
}

Write-Host "== STEP 1: auth + workspace ==" -ForegroundColor Cyan
$companySession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$superSession = $null

$r = Invoke-Api -Step "auth_login_company" -Method "POST" -Path "/auth/login" -ExpectedStatuses @(200) -Session $companySession -Body @{
    username = $CompanyUsername
    password = $Password
}
if (-not $r.Ok) { $abort = $true }

if (-not $abort) {
    $r = Invoke-Api -Step "auth_session_company" -Method "GET" -Path "/auth/session" -ExpectedStatuses @(200) -Session $companySession
    if (-not $r.Ok) { $abort = $true }
}

if (-not $abort) {
    Invoke-Api -Step "auth_invite_activate_probe" -Method "POST" -Path "/auth/invite/activate" -ExpectedStatuses @(200, 400, 404) -Session $companySession -UseCsrf -Body @{
        token = "smoke-invalid-token"
        password = $Password
    } | Out-Null
}

if (-not $abort) {
    $buildings = Invoke-Api -Step "buildings_list" -Method "GET" -Path "/buildings" -ExpectedStatuses @(200) -Session $companySession
    if (-not $buildings.Ok) { $abort = $true }
    $buildingsJson = Parse-JsonSafe -Text $buildings.Content
    $buildingId = "b1"
    if ($buildingsJson -and $buildingsJson.Count -gt 0 -and $buildingsJson[0].id) {
        $buildingId = [string]$buildingsJson[0].id
    }
}

if (-not $abort) {
    $buildingDetail = Invoke-Api -Step "building_detail" -Method "GET" -Path "/buildings/$buildingId" -ExpectedStatuses @(200) -Session $companySession
    if (-not $buildingDetail.Ok) { $abort = $true }
    $detailJson = Parse-JsonSafe -Text $buildingDetail.Content
    $floorId = "1"
    if ($detailJson -and $detailJson.departments -and $detailJson.departments.Count -gt 0 -and $detailJson.departments[0].floor) {
        $floorId = [string]$detailJson.departments[0].floor
    }
}

if (-not $abort) {
    Invoke-Api -Step "building_departments" -Method "GET" -Path "/buildings/$buildingId/departments" -ExpectedStatuses @(200) -Session $companySession | Out-Null
    $workspace = Invoke-Api -Step "floor_workspace" -Method "GET" -Path "/buildings/$buildingId/floors/$floorId/workspace" -ExpectedStatuses @(200) -Session $companySession
    if (-not $workspace.Ok) { $abort = $true }
    $workspaceJson = Parse-JsonSafe -Text $workspace.Content
    $employeeId = "emp-1"
    if ($workspaceJson -and $workspaceJson.employees -and $workspaceJson.employees.Count -gt 0 -and $workspaceJson.employees[0].id) {
        $employeeId = [string]$workspaceJson.employees[0].id
    }

    Invoke-Api -Step "workspace_employee_context" -Method "GET" -Path "/buildings/$buildingId/floors/$floorId/workspace/employee/$employeeId" -ExpectedStatuses @(200) -Session $companySession | Out-Null
    $employeeProfileResp = Invoke-Api -Step "employee_profile" -Method "GET" -Path "/buildings/$buildingId/floors/$floorId/employees/$employeeId/profile" -ExpectedStatuses @(200) -Session $companySession
    $workspaceContextAliasResp = Invoke-Api -Step "workspace_context_alias" -Method "GET" -Path "/buildings/$buildingId/floors/$floorId/workspace-context?employee_id=$employeeId" -ExpectedStatuses @(200) -Session $companySession
    $workspaceContextGlobalAliasResp = Invoke-Api -Step "workspace_context_global_alias" -Method "GET" -Path "/workspace/context?building_id=$buildingId&floor_id=$floorId&employee_id=$employeeId" -ExpectedStatuses @(200) -Session $companySession
    $employeeProfileGlobalAliasResp = Invoke-Api -Step "employee_profile_global_alias" -Method "GET" -Path "/employees/$employeeId/profile?building_id=$buildingId&floor_id=$floorId" -ExpectedStatuses @(200) -Session $companySession

    $legacyPayload = @(
        [string]$workspaceContextAliasResp.Content,
        [string]$workspaceContextGlobalAliasResp.Content,
        [string]$employeeProfileResp.Content,
        [string]$employeeProfileGlobalAliasResp.Content
    ) -join "`n"
    $legacyNoOffsetOk = ($legacyPayload -notlike "*+03:00*")
    Add-Result -Step "legacy_timestamps_no_offset_plus03" -Method "GET" -Path "/workspace-context + /employees/*/profile" -Expected "no +03:00 in payload" -Actual $(if ($legacyNoOffsetOk) { 200 } else { 0 }) -Ok $legacyNoOffsetOk -Note ""
    $legacyHasZuluOk = ($legacyPayload -like "*Z*")
    Add-Result -Step "legacy_timestamps_has_zulu" -Method "GET" -Path "/workspace-context + /employees/*/profile" -Expected "has ISO-8601 Z timestamps" -Actual $(if ($legacyHasZuluOk) { 200 } else { 0 }) -Ok $legacyHasZuluOk -Note ""
}

Write-Host "== STEP 1.5: employee vertical ==" -ForegroundColor Cyan
$employeeSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$employeeLogin = Invoke-Api -Step "auth_login_employee" -Method "POST" -Path "/auth/login" -ExpectedStatuses @(200) -Session $employeeSession -Body @{
    username = $EmployeeUsername
    password = $Password
}
if ($employeeLogin.Ok) {
    $employeeBuildingId = "bcs-drift"
    if (-not [string]::IsNullOrWhiteSpace([string]$buildingId)) { $employeeBuildingId = [string]$buildingId }
    $employeeFloorId = "3"
    if (-not [string]::IsNullOrWhiteSpace([string]$floorId)) { $employeeFloorId = [string]$floorId }

    $workspaceResp = Invoke-Api -Step "employee_workspace" -Method "GET" -Path "/workspace" -ExpectedStatuses @(200) -Session $employeeSession
    $workspaceJson = Parse-JsonSafe -Text $workspaceResp.Content
    $employeeRole = ""
    $employeeTitle = ""
    $timestampFormat = ""
    $todayFocusDate = ""
    if ($workspaceJson) {
        $employeeRole = [string]$workspaceJson.employee.role
        $employeeTitle = [string]$workspaceJson.employee.title
        $timestampFormat = [string]$workspaceJson.contract_meta.timestamp_format
        $todayFocusDate = [string]$workspaceJson.today_focus.date
    }
    $employeeRoleOk = -not [string]::IsNullOrWhiteSpace($employeeRole)
    Add-Result -Step "employee_workspace_role_present" -Method "GET" -Path "/workspace" -Expected "employee.role present" -Actual $(if ($employeeRoleOk) { 200 } else { 0 }) -Ok $employeeRoleOk -Note "role=$employeeRole"
    $employeeTitleOk = -not [string]::IsNullOrWhiteSpace($employeeTitle)
    Add-Result -Step "employee_workspace_title_present" -Method "GET" -Path "/workspace" -Expected "employee.title present" -Actual $(if ($employeeTitleOk) { 200 } else { 0 }) -Ok $employeeTitleOk -Note "title=$employeeTitle"
    $timestampFormatOk = ($timestampFormat -eq "iso-8601-z")
    Add-Result -Step "employee_workspace_timestamp_format" -Method "GET" -Path "/workspace" -Expected "contract_meta.timestamp_format=iso-8601-z" -Actual $(if ($timestampFormatOk) { 200 } else { 0 }) -Ok $timestampFormatOk -Note "actual=$timestampFormat"
    $todayFocusDateOk = ($todayFocusDate -match "^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
    Add-Result -Step "employee_workspace_today_focus_iso" -Method "GET" -Path "/workspace" -Expected "ISO-8601 Z timestamp" -Actual $(if ($todayFocusDateOk) { 200 } else { 0 }) -Ok $todayFocusDateOk -Note "date=$todayFocusDate"

    $meResp = Invoke-Api -Step "employee_me_owner" -Method "GET" -Path "/employees/me" -ExpectedStatuses @(200) -Session $employeeSession
    $meJson = Parse-JsonSafe -Text $meResp.Content
    $ownEmployeeId = [string]$meJson.header.id
    $ownerSot = [string]$meJson.header.role_source_of_truth
    $ownerSotOk = ($ownerSot -eq "role")
    Add-Result -Step "employee_me_role_source_of_truth" -Method "GET" -Path "/employees/me" -Expected "header.role_source_of_truth=role" -Actual $(if ($ownerSotOk) { 200 } else { 0 }) -Ok $ownerSotOk -Note "actual=$ownerSot"

    if (-not [string]::IsNullOrWhiteSpace($ownEmployeeId)) {
        Invoke-Api -Step "employee_profile_owner_by_id" -Method "GET" -Path "/employees/$ownEmployeeId" -ExpectedStatuses @(200) -Session $employeeSession | Out-Null
    }
    $publicResp = Invoke-Api -Step "employee_profile_public" -Method "GET" -Path "/employees/emp-2" -ExpectedStatuses @(200) -Session $employeeSession
    $publicJson = Parse-JsonSafe -Text $publicResp.Content
    $publicView = [string]$publicJson.view
    $publicViewOk = ($publicView -eq "public")
    Add-Result -Step "employee_profile_public_view" -Method "GET" -Path "/employees/emp-2" -Expected "view=public" -Actual $(if ($publicViewOk) { 200 } else { 0 }) -Ok $publicViewOk -Note "view=$publicView"
    $publicNoPerfOk = ($null -eq $publicJson.performance)
    Add-Result -Step "employee_profile_public_no_performance" -Method "GET" -Path "/employees/emp-2" -Expected "no performance in public profile" -Actual $(if ($publicNoPerfOk) { 200 } else { 0 }) -Ok $publicNoPerfOk -Note ""
    $publicNoPreferencesOk = ($null -eq $publicJson.preferences)
    Add-Result -Step "employee_profile_public_no_preferences" -Method "GET" -Path "/employees/emp-2" -Expected "no preferences in public profile" -Actual $(if ($publicNoPreferencesOk) { 200 } else { 0 }) -Ok $publicNoPreferencesOk -Note ""
    $publicNoPersonalEmailOk = ($null -eq $publicJson.contacts.personal_email)
    Add-Result -Step "employee_profile_public_no_personal_email" -Method "GET" -Path "/employees/emp-2" -Expected "no personal_email in public contacts" -Actual $(if ($publicNoPersonalEmailOk) { 200 } else { 0 }) -Ok $publicNoPersonalEmailOk -Note ""
    $publicNoPhoneOk = ($null -eq $publicJson.contacts.phone)
    Add-Result -Step "employee_profile_public_no_phone" -Method "GET" -Path "/employees/emp-2" -Expected "no phone in public contacts" -Actual $(if ($publicNoPhoneOk) { 200 } else { 0 }) -Ok $publicNoPhoneOk -Note ""

    $workspaceTasksScope = "/workspace/tasks?building_id=$employeeBuildingId&floor_id=$employeeFloorId"
    Invoke-Api -Step "workspace_tasks_alias_missing_scope" -Method "GET" -Path "/workspace/tasks" -ExpectedStatuses @(400) -Session $employeeSession | Out-Null
    Invoke-Api -Step "workspace_tasks_alias_list" -Method "GET" -Path $workspaceTasksScope -ExpectedStatuses @(200) -Session $employeeSession | Out-Null
    Invoke-Api -Step "workspace_tasks_alias_filter_column" -Method "GET" -Path "$workspaceTasksScope&column=todo" -ExpectedStatuses @(200) -Session $employeeSession | Out-Null

    $employeeCsrf = Get-CsrfToken -Session $employeeSession -Origin $BaseUrl
    if (-not [string]::IsNullOrWhiteSpace($employeeCsrf)) {
        $workspaceTaskCreateResp = Invoke-Api -Step "workspace_task_alias_create" -Method "POST" -Path $workspaceTasksScope -ExpectedStatuses @(201) -Session $employeeSession -UseCsrf -Body @{
            title = "Workspace task alias smoke $(Get-Date -Format HHmmss)"
            column = "todo"
            priority = "medium"
        }
        $workspaceTaskId = $null
        if ($workspaceTaskCreateResp.Ok) {
            $workspaceTaskCreateJson = Parse-JsonSafe -Text $workspaceTaskCreateResp.Content
            if ($workspaceTaskCreateJson -and $workspaceTaskCreateJson.id) {
                $workspaceTaskId = [string]$workspaceTaskCreateJson.id
            }
        }
        if ($workspaceTaskId) {
            Invoke-Api -Step "workspace_task_alias_detail" -Method "GET" -Path "/workspace/tasks/${workspaceTaskId}?building_id=${employeeBuildingId}&floor_id=${employeeFloorId}" -ExpectedStatuses @(200) -Session $employeeSession | Out-Null
            Invoke-Api -Step "workspace_task_alias_patch" -Method "PATCH" -Path "/workspace/tasks/${workspaceTaskId}?building_id=${employeeBuildingId}&floor_id=${employeeFloorId}" -ExpectedStatuses @(200) -Session $employeeSession -UseCsrf -Body @{
                column = "in_progress"
                priority = "high"
            } | Out-Null
            Invoke-Api -Step "workspace_task_alias_delete" -Method "DELETE" -Path "/workspace/tasks/${workspaceTaskId}?building_id=${employeeBuildingId}&floor_id=${employeeFloorId}" -ExpectedStatuses @(204) -Session $employeeSession -UseCsrf | Out-Null
            Invoke-Api -Step "workspace_task_alias_detail_after_delete" -Method "GET" -Path "/workspace/tasks/${workspaceTaskId}?building_id=${employeeBuildingId}&floor_id=${employeeFloorId}" -ExpectedStatuses @(404) -Session $employeeSession | Out-Null
        }

        Invoke-Api -Step "employee_me_patch" -Method "PATCH" -Path "/employees/me" -ExpectedStatuses @(200) -Session $employeeSession -UseCsrf -Body @{
            city = "Moscow"
            preferences = @{ ai_suggestions = $true }
        } | Out-Null
        Invoke-Api -Step "employee_quick_task_create" -Method "POST" -Path "/workspace/quick-tasks" -ExpectedStatuses @(201) -Session $employeeSession -UseCsrf -Body @{
            title = "Employee vertical smoke $(Get-Date -Format HHmmss)"
            slot = "today"
            priority = "high"
            project_id = "pr-1"
        } | Out-Null
    } else {
        Add-Result -Step "employee_csrf_token_present" -Method "GET" -Path "/auth/login" -Expected "csrftoken cookie present" -Actual 0 -Ok $false -Note "csrf cookie missing"
    }
}

Write-Host "== STEP 2: projects ==" -ForegroundColor Cyan
$projectsList = Invoke-Api -Step "projects_list" -Method "GET" -Path "/projects" -ExpectedStatuses @(200) -Session $companySession
Invoke-Api -Step "projects_filter_status" -Method "GET" -Path "/projects?status=active" -ExpectedStatuses @(200) -Session $companySession | Out-Null
Invoke-Api -Step "projects_filter_q" -Method "GET" -Path "/projects?q=demo" -ExpectedStatuses @(200) -Session $companySession | Out-Null

$employeesResp = Invoke-Api -Step "employees_list_for_project_member" -Method "GET" -Path "/employees" -ExpectedStatuses @(200) -Session $companySession
$memberUserId = $null
$employeesJson = Parse-JsonSafe -Text $employeesResp.Content
$employeeItems = Get-ItemsFromListPayload -Payload $employeesJson
if ($employeeItems.Count -gt 0) {
    $memberUserId = $employeeItems[0].id
}

$projectName = "Smoke Runner Project $(Get-Date -Format yyyyMMddHHmmss)"
$createProjectTry1 = Invoke-Api -Step "project_create_try_org_1" -Method "POST" -Path "/projects" -ExpectedStatuses @(201, 400) -Session $companySession -UseCsrf -Body @{
    organization = 1
    name = $projectName
    description = "Created by SMOKE_RUNNER.ps1"
    status = "active"
}
$createProject = $createProjectTry1
if ($createProjectTry1.StatusCode -eq 400) {
    $createProject = Invoke-Api -Step "project_create_try_no_org" -Method "POST" -Path "/projects" -ExpectedStatuses @(201) -Session $companySession -UseCsrf -Body @{
        name = $projectName
        description = "Created by SMOKE_RUNNER.ps1"
        status = "active"
    }
}
$projectCreateOk = ($createProject.StatusCode -eq 201)
Add-Result `
    -Step "project_create" `
    -Method "POST" `
    -Path "/projects" `
    -Expected "201" `
    -Actual $createProject.StatusCode `
    -Ok $projectCreateOk `
    -Note "name=$projectName"
$projectId = $null
if ($projectCreateOk) {
    $createJson = Parse-JsonSafe -Text $createProject.Content
    if ($createJson -and $createJson.id) {
        $projectId = [string]$createJson.id
    }
}
if (-not $projectId) {
    $projectsJson = Parse-JsonSafe -Text $projectsList.Content
    $projectItems = Get-ItemsFromListPayload -Payload $projectsJson
    if ($projectItems.Count -gt 0) {
        $projectId = [string]$projectItems[0].id
    }
}
if (-not $projectId) { $projectId = "1" }

Invoke-Api -Step "project_detail" -Method "GET" -Path "/projects/$projectId" -ExpectedStatuses @(200) -Session $companySession | Out-Null
Invoke-Api -Step "project_patch" -Method "PATCH" -Path "/projects/$projectId" -ExpectedStatuses @(200) -Session $companySession -UseCsrf -Body @{
    description = "Patched by SMOKE_RUNNER.ps1"
    status = "on_hold"
} | Out-Null
Invoke-Api -Step "project_archive" -Method "POST" -Path "/projects/$projectId/archive" -ExpectedStatuses @(200) -Session $companySession -UseCsrf -Body @{} | Out-Null
Invoke-Api -Step "project_restore" -Method "POST" -Path "/projects/$projectId/restore" -ExpectedStatuses @(200) -Session $companySession -UseCsrf -Body @{} | Out-Null
Invoke-Api -Step "project_members_list" -Method "GET" -Path "/projects/$projectId/members" -ExpectedStatuses @(200) -Session $companySession | Out-Null

if ($memberUserId) {
    $memberCreate = Invoke-Api -Step "project_member_create" -Method "POST" -Path "/projects/$projectId/members" -ExpectedStatuses @(201) -Session $companySession -UseCsrf -Body @{
        user = $memberUserId
        role = "editor"
        is_active = $true
    }
    $memberId = $null
    if ($memberCreate.Ok) {
        $memberJson = Parse-JsonSafe -Text $memberCreate.Content
        if ($memberJson -and $memberJson.id) {
            $memberId = [string]$memberJson.id
        }
    }
    if ($memberId) {
        Invoke-Api -Step "project_member_patch" -Method "PATCH" -Path "/projects/$projectId/members/$memberId" -ExpectedStatuses @(200) -Session $companySession -UseCsrf -Body @{
            role = "viewer"
        } | Out-Null
        Invoke-Api -Step "project_member_delete" -Method "DELETE" -Path "/projects/$projectId/members/$memberId" -ExpectedStatuses @(204) -Session $companySession -UseCsrf | Out-Null
    }
}

Write-Host "== STEP 2.5: tasks ==" -ForegroundColor Cyan
Invoke-Api -Step "tasks_list" -Method "GET" -Path "/tasks" -ExpectedStatuses @(200) -Session $companySession | Out-Null
Invoke-Api -Step "tasks_filter_status" -Method "GET" -Path "/tasks?status=todo" -ExpectedStatuses @(200) -Session $companySession | Out-Null
Invoke-Api -Step "tasks_filter_priority" -Method "GET" -Path "/tasks?priority=high" -ExpectedStatuses @(200) -Session $companySession | Out-Null
$tasksInvalidStatusResp = Invoke-Api -Step "tasks_filter_status_invalid" -Method "GET" -Path "/tasks?status=invalid_status" -ExpectedStatuses @(400) -Session $companySession
$tasksInvalidStatusContent = [string]$tasksInvalidStatusResp.Content
$tasksInvalidStatusDetailOk = [string]::IsNullOrWhiteSpace($tasksInvalidStatusContent) -or ($tasksInvalidStatusContent -like "*Allowed:*")
Add-Result `
    -Step "tasks_filter_status_invalid_detail" `
    -Method "GET" `
    -Path "/tasks?status=invalid_status" `
    -Expected "detail contains Allowed:" `
    -Actual $(if ($tasksInvalidStatusDetailOk) { 200 } else { 0 }) `
    -Ok $tasksInvalidStatusDetailOk `
    -Note ""
Invoke-Api -Step "tasks_filter_priority_invalid" -Method "GET" -Path "/tasks?priority=invalid_priority" -ExpectedStatuses @(400) -Session $companySession | Out-Null
Invoke-Api -Step "tasks_stats" -Method "GET" -Path "/tasks/stats" -ExpectedStatuses @(200) -Session $companySession | Out-Null
Invoke-Api -Step "tasks_board" -Method "GET" -Path "/tasks/board" -ExpectedStatuses @(200) -Session $companySession | Out-Null
Invoke-Api -Step "tasks_board_priority_invalid" -Method "GET" -Path "/tasks/board?priority=invalid_priority" -ExpectedStatuses @(400) -Session $companySession | Out-Null

$tasksCursorResp = Invoke-Api -Step "tasks_list_cursor_first" -Method "GET" -Path "/tasks?cursor=&page_size=2" -ExpectedStatuses @(200) -Session $companySession
$tasksCursorJson = Parse-JsonSafe -Text $tasksCursorResp.Content
$nextTasksCursor = $null
if ($tasksCursorJson -and $tasksCursorJson.next_cursor) {
    $nextTasksCursor = [string]$tasksCursorJson.next_cursor
}
if (-not [string]::IsNullOrWhiteSpace($nextTasksCursor)) {
    $encodedCursor = [System.Uri]::EscapeDataString($nextTasksCursor)
    Invoke-Api -Step "tasks_list_cursor_next" -Method "GET" -Path "/tasks?cursor=$encodedCursor&page_size=2" -ExpectedStatuses @(200) -Session $companySession | Out-Null
}
Invoke-Api -Step "tasks_list_cursor_invalid" -Method "GET" -Path "/tasks?cursor=invalid&page_size=2" -ExpectedStatuses @(400) -Session $companySession | Out-Null

$taskAssigneeId = 12
$tmpAssignee = 0
if ([int]::TryParse([string]$memberUserId, [ref]$tmpAssignee) -and $tmpAssignee -in @(11, 12, 13)) {
    $taskAssigneeId = $tmpAssignee
}
$taskProjectId = $null
$tmpProject = 0
if ([int]::TryParse([string]$projectId, [ref]$tmpProject)) {
    $taskProjectId = $tmpProject
}

$taskCreateBody = @{
    title = "Smoke Task $(Get-Date -Format yyyyMMddHHmmss)"
    description = "Created by SMOKE_RUNNER.ps1"
    status = "todo"
    priority = "medium"
    assignee_id = $taskAssigneeId
}
if ($null -ne $taskProjectId) {
    $taskCreateBody["project_id"] = $taskProjectId
}

Invoke-Api -Step "task_create_invalid_assignee" -Method "POST" -Path "/tasks" -ExpectedStatuses @(400) -Session $companySession -UseCsrf -Body @{
    title = "Invalid assignee smoke"
    assignee_id = 999999
    status = "todo"
    priority = "medium"
} | Out-Null

$taskCreateResp = Invoke-Api -Step "task_create" -Method "POST" -Path "/tasks" -ExpectedStatuses @(201) -Session $companySession -UseCsrf -Body $taskCreateBody
$taskId = $null
if ($taskCreateResp.Ok) {
    $taskCreateJson = Parse-JsonSafe -Text $taskCreateResp.Content
    if ($taskCreateJson -and $taskCreateJson.id) {
        $taskId = [string]$taskCreateJson.id
    }
}

if ($taskId) {
    Invoke-Api -Step "task_detail" -Method "GET" -Path "/tasks/$taskId" -ExpectedStatuses @(200) -Session $companySession | Out-Null
    Invoke-Api -Step "task_patch" -Method "PATCH" -Path "/tasks/$taskId" -ExpectedStatuses @(200) -Session $companySession -UseCsrf -Body @{
        status = "in_progress"
        priority = "high"
        description = "Patched by SMOKE_RUNNER.ps1"
    } | Out-Null
    Invoke-Api -Step "tasks_bulk_status" -Method "PATCH" -Path "/tasks/bulk/status" -ExpectedStatuses @(200) -Session $companySession -UseCsrf -Body @{
        task_ids = @([int]$taskId)
        status = "done"
    } | Out-Null
    Invoke-Api -Step "tasks_bulk_status_duplicate_ids" -Method "PATCH" -Path "/tasks/bulk/status" -ExpectedStatuses @(400) -Session $companySession -UseCsrf -Body @{
        task_ids = @([int]$taskId, [int]$taskId)
        status = "done"
    } | Out-Null
    Invoke-Api -Step "tasks_bulk_assign" -Method "PATCH" -Path "/tasks/bulk/assign" -ExpectedStatuses @(200) -Session $companySession -UseCsrf -Body @{
        task_ids = @([int]$taskId)
        assignee_id = $taskAssigneeId
    } | Out-Null
    Invoke-Api -Step "tasks_bulk_assign_invalid_assignee" -Method "PATCH" -Path "/tasks/bulk/assign" -ExpectedStatuses @(400) -Session $companySession -UseCsrf -Body @{
        task_ids = @([int]$taskId)
        assignee_id = 999999
    } | Out-Null

    $taskActivityResp = Invoke-Api -Step "task_activity_list" -Method "GET" -Path "/tasks/$taskId/activity?page=1&page_size=5" -ExpectedStatuses @(200) -Session $companySession
    $taskActivityJson = Parse-JsonSafe -Text $taskActivityResp.Content
    $nextActivityCursor = $null
    if ($taskActivityJson -and $taskActivityJson.next_cursor) {
        $nextActivityCursor = [string]$taskActivityJson.next_cursor
    }
    if (-not [string]::IsNullOrWhiteSpace($nextActivityCursor)) {
        $encodedActivityCursor = [System.Uri]::EscapeDataString($nextActivityCursor)
        Invoke-Api -Step "task_activity_cursor_next" -Method "GET" -Path "/tasks/$taskId/activity?cursor=$encodedActivityCursor&page_size=2" -ExpectedStatuses @(200) -Session $companySession | Out-Null
    }
    Invoke-Api -Step "task_activity_cursor_invalid" -Method "GET" -Path "/tasks/$taskId/activity?cursor=invalid&page_size=2" -ExpectedStatuses @(400) -Session $companySession | Out-Null

    Invoke-Api -Step "task_delete" -Method "DELETE" -Path "/tasks/$taskId" -ExpectedStatuses @(204) -Session $companySession -UseCsrf | Out-Null
    Invoke-Api -Step "task_detail_after_delete" -Method "GET" -Path "/tasks/$taskId" -ExpectedStatuses @(404) -Session $companySession | Out-Null
}

if ($Mode -eq "Full") {
    Write-Host "== STEP 3: company admin ==" -ForegroundColor Cyan
    Invoke-Api -Step "company_overview" -Method "GET" -Path "/company/admin/overview" -ExpectedStatuses @(200) -Session $companySession | Out-Null
    Invoke-Api -Step "company_departments" -Method "GET" -Path "/company/admin/departments" -ExpectedStatuses @(200) -Session $companySession | Out-Null
    Invoke-Api -Step "company_users" -Method "GET" -Path "/company/admin/users?q=demo" -ExpectedStatuses @(200) -Session $companySession | Out-Null
    $companyUsersInvalidRoleResp = Invoke-Api -Step "company_users_invalid_role_filter" -Method "GET" -Path "/company/admin/users?role=invalid_role" -ExpectedStatuses @(400) -Session $companySession
    $companyUsersInvalidRoleContent = [string]$companyUsersInvalidRoleResp.Content
    $companyUsersInvalidRoleDetailOk = [string]::IsNullOrWhiteSpace($companyUsersInvalidRoleContent) -or ($companyUsersInvalidRoleContent -like "*Allowed:*")
    Add-Result `
        -Step "company_users_invalid_role_filter_detail" `
        -Method "GET" `
        -Path "/company/admin/users?role=invalid_role" `
        -Expected "detail contains Allowed:" `
        -Actual $(if ($companyUsersInvalidRoleDetailOk) { 200 } else { 0 }) `
        -Ok $companyUsersInvalidRoleDetailOk `
        -Note ""
    Invoke-Api -Step "company_users_invalid_status_filter" -Method "GET" -Path "/company/admin/users?status=invalid_status" -ExpectedStatuses @(400) -Session $companySession | Out-Null
    Invoke-Api -Step "company_invites" -Method "GET" -Path "/company/admin/invites" -ExpectedStatuses @(200) -Session $companySession | Out-Null

    Invoke-Api -Step "alias_company_overview" -Method "GET" -Path "/admin/company/overview" -ExpectedStatuses @(200) -Session $companySession | Out-Null
    Invoke-Api -Step "alias_company_departments" -Method "GET" -Path "/admin/company/departments" -ExpectedStatuses @(200) -Session $companySession | Out-Null
    Invoke-Api -Step "alias_company_users" -Method "GET" -Path "/admin/company/users?q=demo" -ExpectedStatuses @(200) -Session $companySession | Out-Null
    Invoke-Api -Step "alias_company_invites" -Method "GET" -Path "/admin/company/invites" -ExpectedStatuses @(200) -Session $companySession | Out-Null

    $usersResp = Invoke-Api -Step "company_users_all" -Method "GET" -Path "/company/admin/users" -ExpectedStatuses @(200) -Session $companySession -Silent
    $usersJson = Parse-JsonSafe -Text $usersResp.Content
    $users = Get-ItemsFromListPayload -Payload $usersJson
    if ($users.Count -gt 0) {
        $targetUserId = [string]$users[0].id
        Invoke-Api -Step "company_user_role_update" -Method "PATCH" -Path "/company/admin/users/$targetUserId/role" -ExpectedStatuses @(200) -Session $companySession -UseCsrf -Body @{ role = "manager" } | Out-Null
        Invoke-Api -Step "alias_company_user_role_update" -Method "PATCH" -Path "/admin/company/users/$targetUserId/role" -ExpectedStatuses @(200) -Session $companySession -UseCsrf -Body @{ role = "employee" } | Out-Null
        Invoke-Api -Step "company_user_role_update_invalid_role" -Method "PATCH" -Path "/company/admin/users/$targetUserId/role" -ExpectedStatuses @(400) -Session $companySession -UseCsrf -Body @{ role = "invalid_role" } | Out-Null
    }
    Invoke-Api -Step "company_user_role_update_not_found" -Method "PATCH" -Path "/company/admin/users/999999/role" -ExpectedStatuses @(404) -Session $companySession -UseCsrf -Body @{ role = "employee" } | Out-Null

    $inviteCreate = Invoke-Api -Step "company_invite_create" -Method "POST" -Path "/company/admin/invites" -ExpectedStatuses @(201) -Session $companySession -UseCsrf -Body @{
        email = "smoke.invite@atom.local"
        role = "employee"
    }
    Invoke-Api -Step "company_invite_create_invalid_role" -Method "POST" -Path "/company/admin/invites" -ExpectedStatuses @(400) -Session $companySession -UseCsrf -Body @{
        email = "smoke.invalid.role@atom.local"
        role = "invalid_role"
    } | Out-Null
    if ($inviteCreate.Ok) {
        $inviteJson = Parse-JsonSafe -Text $inviteCreate.Content
        if ($inviteJson -and $inviteJson.id) {
            Invoke-Api -Step "company_invite_revoke" -Method "POST" -Path "/company/admin/invites/$($inviteJson.id)/revoke" -ExpectedStatuses @(200) -Session $companySession -UseCsrf -Body @{} | Out-Null
        }
    }
    Invoke-Api -Step "company_invite_revoke_not_found" -Method "POST" -Path "/company/admin/invites/999999/revoke" -ExpectedStatuses @(404) -Session $companySession -UseCsrf -Body @{} | Out-Null

    $aliasInviteCreate = Invoke-Api -Step "alias_company_invite_create" -Method "POST" -Path "/admin/company/invites" -ExpectedStatuses @(201) -Session $companySession -UseCsrf -Body @{
        email = "smoke.alias.invite@atom.local"
        role = "employee"
    }
    if ($aliasInviteCreate.Ok) {
        $aliasInviteJson = Parse-JsonSafe -Text $aliasInviteCreate.Content
        if ($aliasInviteJson -and $aliasInviteJson.id) {
            Invoke-Api -Step "alias_company_invite_revoke" -Method "POST" -Path "/admin/company/invites/$($aliasInviteJson.id)/revoke" -ExpectedStatuses @(200) -Session $companySession -UseCsrf -Body @{} | Out-Null
        }
    }

    Write-Host "== STEP 4: super admin + audit + action ==" -ForegroundColor Cyan
    $superSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $r = Invoke-Api -Step "auth_login_super" -Method "POST" -Path "/auth/login" -ExpectedStatuses @(200) -Session $superSession -Body @{
        username = $SuperUsername
        password = $Password
    }
    if (-not $r.Ok) { $abort = $true }

    Invoke-Api -Step "platform_overview" -Method "GET" -Path "/admin/platform/overview" -ExpectedStatuses @(200) -Session $superSession | Out-Null
    Invoke-Api -Step "platform_tenants" -Method "GET" -Path "/admin/platform/tenants" -ExpectedStatuses @(200) -Session $superSession | Out-Null
    Invoke-Api -Step "platform_tenants_invalid_status_filter" -Method "GET" -Path "/admin/platform/tenants?status=invalid_status" -ExpectedStatuses @(400) -Session $superSession | Out-Null
    Invoke-Api -Step "platform_users" -Method "GET" -Path "/admin/platform/users" -ExpectedStatuses @(200) -Session $superSession | Out-Null
    Invoke-Api -Step "platform_invites" -Method "GET" -Path "/admin/platform/invites" -ExpectedStatuses @(200) -Session $superSession | Out-Null
    Invoke-Api -Step "platform_audit_stats" -Method "GET" -Path "/admin/platform/audit/stats" -ExpectedStatuses @(200) -Session $superSession | Out-Null
    $auditEvents = Invoke-Api -Step "platform_audit_events" -Method "GET" -Path "/admin/platform/audit/events?page=1&page_size=5" -ExpectedStatuses @(200) -Session $superSession
    Invoke-Api -Step "platform_audit_events_cursor" -Method "GET" -Path "/admin/platform/audit/events?cursor=&page_size=2" -ExpectedStatuses @(200) -Session $superSession | Out-Null
    Invoke-Api -Step "platform_audit_events_invalid_severity" -Method "GET" -Path "/admin/platform/audit/events?severity=invalid_severity" -ExpectedStatuses @(400) -Session $superSession | Out-Null
    Invoke-Api -Step "platform_audit_events_invalid_status" -Method "GET" -Path "/admin/platform/audit/events?status=invalid_status" -ExpectedStatuses @(400) -Session $superSession | Out-Null

    Invoke-Api -Step "admin_actions_stats" -Method "GET" -Path "/admin/actions/stats" -ExpectedStatuses @(200) -Session $superSession | Out-Null
    $actionsEvents = Invoke-Api -Step "admin_actions_events" -Method "GET" -Path "/admin/actions/events?page=1&page_size=5" -ExpectedStatuses @(200) -Session $superSession
    Invoke-Api -Step "admin_actions_events_cursor" -Method "GET" -Path "/admin/actions/events?cursor=&page_size=2" -ExpectedStatuses @(200) -Session $superSession | Out-Null
    Invoke-Api -Step "admin_actions_events_invalid_scope" -Method "GET" -Path "/admin/actions/events?scope=invalid_scope" -ExpectedStatuses @(400) -Session $superSession | Out-Null
    Invoke-Api -Step "admin_actions_events_invalid_severity" -Method "GET" -Path "/admin/actions/events?severity=invalid_severity" -ExpectedStatuses @(400) -Session $superSession | Out-Null
    Invoke-Api -Step "admin_actions_events_invalid_status" -Method "GET" -Path "/admin/actions/events?status=invalid_status" -ExpectedStatuses @(400) -Session $superSession | Out-Null

    $actionJson = Parse-JsonSafe -Text $actionsEvents.Content
    $actionItems = Get-ItemsFromListPayload -Payload $actionJson
    if ($actionItems.Count -gt 0 -and $actionItems[0].id) {
        Invoke-Api -Step "admin_action_detail" -Method "GET" -Path "/admin/actions/events/$($actionItems[0].id)" -ExpectedStatuses @(200) -Session $superSession | Out-Null
    }

    Invoke-Api -Step "alias_platform_overview" -Method "GET" -Path "/platform/admin/overview" -ExpectedStatuses @(200) -Session $superSession | Out-Null
    Invoke-Api -Step "alias_platform_tenants" -Method "GET" -Path "/platform/admin/tenants" -ExpectedStatuses @(200) -Session $superSession | Out-Null
    Invoke-Api -Step "alias_platform_users" -Method "GET" -Path "/platform/admin/users" -ExpectedStatuses @(200) -Session $superSession | Out-Null
    Invoke-Api -Step "alias_platform_invites" -Method "GET" -Path "/platform/admin/invites" -ExpectedStatuses @(200) -Session $superSession | Out-Null
    Invoke-Api -Step "alias_audit_stats" -Method "GET" -Path "/platform/admin/audit/stats" -ExpectedStatuses @(200) -Session $superSession | Out-Null
    Invoke-Api -Step "alias_audit_events" -Method "GET" -Path "/platform/admin/audit/events?page=1&page_size=5" -ExpectedStatuses @(200) -Session $superSession | Out-Null

    $tenantCreate = Invoke-Api -Step "platform_tenant_create" -Method "POST" -Path "/admin/platform/tenants" -ExpectedStatuses @(201) -Session $superSession -UseCsrf -Body @{
        name = "Smoke Tenant $(Get-Date -Format HHmmss)"
    }
    if ($tenantCreate.Ok) {
        $tenantJson = Parse-JsonSafe -Text $tenantCreate.Content
        if ($tenantJson -and $tenantJson.id) {
            Invoke-Api -Step "platform_tenant_status_patch" -Method "PATCH" -Path "/admin/platform/tenants/$($tenantJson.id)/status" -ExpectedStatuses @(200) -Session $superSession -UseCsrf -Body @{
                status = "active"
            } | Out-Null
            Invoke-Api -Step "alias_platform_tenant_status_patch" -Method "PATCH" -Path "/platform/admin/tenants/$($tenantJson.id)/status" -ExpectedStatuses @(200) -Session $superSession -UseCsrf -Body @{
                status = "trial"
            } | Out-Null
            Invoke-Api -Step "platform_tenant_status_patch_invalid_status" -Method "PATCH" -Path "/admin/platform/tenants/$($tenantJson.id)/status" -ExpectedStatuses @(400) -Session $superSession -UseCsrf -Body @{
                status = "invalid_status"
            } | Out-Null
        }
    }
    Invoke-Api -Step "platform_tenant_status_patch_not_found" -Method "PATCH" -Path "/admin/platform/tenants/999999/status" -ExpectedStatuses @(404) -Session $superSession -UseCsrf -Body @{
        status = "active"
    } | Out-Null

    $platformInviteCreate = Invoke-Api -Step "platform_invite_create" -Method "POST" -Path "/admin/platform/invites" -ExpectedStatuses @(201) -Session $superSession -UseCsrf -Body @{
        email = "smoke.platform@atom.local"
        role = "support"
    }
    Invoke-Api -Step "platform_invite_create_invalid_role" -Method "POST" -Path "/admin/platform/invites" -ExpectedStatuses @(400) -Session $superSession -UseCsrf -Body @{
        email = "smoke.platform.invalid.role@atom.local"
        role = "invalid_role"
    } | Out-Null
    if ($platformInviteCreate.Ok) {
        $platformInviteJson = Parse-JsonSafe -Text $platformInviteCreate.Content
        if ($platformInviteJson -and $platformInviteJson.id) {
            Invoke-Api -Step "platform_invite_revoke" -Method "POST" -Path "/admin/platform/invites/$($platformInviteJson.id)/revoke" -ExpectedStatuses @(200) -Session $superSession -UseCsrf -Body @{} | Out-Null
        }
    }
    Invoke-Api -Step "platform_invite_revoke_not_found" -Method "POST" -Path "/admin/platform/invites/999999/revoke" -ExpectedStatuses @(404) -Session $superSession -UseCsrf -Body @{} | Out-Null

    $platformInviteCreateForAlias = Invoke-Api -Step "platform_invite_create_for_alias_revoke" -Method "POST" -Path "/admin/platform/invites" -ExpectedStatuses @(201) -Session $superSession -UseCsrf -Body @{
        email = "smoke.platform.alias.$(Get-Date -Format HHmmss)@atom.local"
        role = "support"
    }
    if ($platformInviteCreateForAlias.Ok) {
        $platformInviteAliasJson = Parse-JsonSafe -Text $platformInviteCreateForAlias.Content
        if ($platformInviteAliasJson -and $platformInviteAliasJson.id) {
            Invoke-Api -Step "alias_platform_invite_revoke" -Method "POST" -Path "/platform/admin/invites/$($platformInviteAliasJson.id)/revoke" -ExpectedStatuses @(200) -Session $superSession -UseCsrf -Body @{} | Out-Null
        }
    }

    $exportResp = Invoke-Api -Step "platform_audit_export" -Method "GET" -Path "/admin/platform/audit/export" -ExpectedStatuses @(200) -Session $superSession -Silent
    $ct = [string]$exportResp.Headers["Content-Type"]
    $cd = [string]$exportResp.Headers["Content-Disposition"]
    $csvOk = ($ct -like "*text/csv*") -and ($cd -like "*platform-audit-*")
    Add-Result `
        -Step "platform_audit_export_headers" `
        -Method "GET" `
        -Path "/admin/platform/audit/export" `
        -Expected "text/csv + Content-Disposition" `
        -Actual ($(if ($csvOk) { 200 } else { 0 })) `
        -Ok $csvOk `
        -Note "ct=$ct; cd=$cd"

    $aliasExportResp = Invoke-Api -Step "alias_platform_audit_export" -Method "GET" -Path "/platform/admin/audit/export" -ExpectedStatuses @(200) -Session $superSession -Silent
    $aliasCt = [string]$aliasExportResp.Headers["Content-Type"]
    $aliasCd = [string]$aliasExportResp.Headers["Content-Disposition"]
    $aliasCsvOk = ($aliasCt -like "*text/csv*") -and ($aliasCd -like "*platform-audit-*")
    Add-Result `
        -Step "alias_platform_audit_export_headers" `
        -Method "GET" `
        -Path "/platform/admin/audit/export" `
        -Expected "text/csv + Content-Disposition" `
        -Actual ($(if ($aliasCsvOk) { 200 } else { 0 })) `
        -Ok $aliasCsvOk `
        -Note "ct=$aliasCt; cd=$aliasCd"
} else {
    Write-Host "Skipping STEP 3/4 in Fast mode" -ForegroundColor Yellow
}

Invoke-Api -Step "auth_logout_company" -Method "POST" -Path "/auth/logout" -ExpectedStatuses @(200, 204) -Session $companySession -UseCsrf -Body @{} | Out-Null
if ($Mode -eq "Full" -and $superSession) {
    Invoke-Api -Step "auth_logout_super" -Method "POST" -Path "/auth/logout" -ExpectedStatuses @(200, 204) -Session $superSession -UseCsrf -Body @{} | Out-Null
}

Write-Host ""
Write-Host "== Smoke Summary ==" -ForegroundColor Cyan
$script:Results | Sort-Object step | Format-Table -AutoSize

$failed = @($script:Results | Where-Object { -not $_.ok })
$summary = [pscustomobject]@{
    mode = $Mode
    base_url = $BaseUrl
    generated_at = (Get-Date).ToString("o")
    total_checks = $script:Results.Count
    failed_checks = $failed.Count
    results = $script:Results
}

if (-not [string]::IsNullOrWhiteSpace($JsonReportPath)) {
    $reportDir = Split-Path -Path $JsonReportPath -Parent
    if (-not [string]::IsNullOrWhiteSpace($reportDir) -and -not (Test-Path -Path $reportDir)) {
        New-Item -ItemType Directory -Path $reportDir -Force | Out-Null
    }
    $summary | ConvertTo-Json -Depth 8 | Set-Content -Path $JsonReportPath -Encoding UTF8
    Write-Host "JSON report written to: $JsonReportPath" -ForegroundColor Cyan
}

Write-Host ""
if ($failed.Count -gt 0) {
    Write-Host "FAILED checks: $($failed.Count)" -ForegroundColor Red
    exit 1
}

Write-Host "All checks passed: $($script:Results.Count)" -ForegroundColor Green
exit 0
