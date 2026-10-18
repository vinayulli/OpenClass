param(
    [string]$ProjectId = 'hackathon-506016',
    [string]$Region = 'us-central1',
    [switch]$Apply
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($ProjectId -notmatch '^[a-z][a-z0-9-]{4,61}[a-z0-9]$') { throw 'Invalid project ID' }
if ($Region -notmatch '^[a-z]+-[a-z]+[0-9]$') { throw 'Invalid region' }
$configRoot = Join-Path $PSScriptRoot 'generated'
New-Item -ItemType Directory -Path $configRoot -Force | Out-Null
Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'gateway') -File | ForEach-Object {
    $content = (Get-Content -LiteralPath $_.FullName -Raw).Replace('PROJECT_ID', $ProjectId).Replace('REGION', $Region)
    $name = $_.Name.Replace('.example', '')
    Set-Content -LiteralPath (Join-Path $configRoot $name) -Value $content -Encoding UTF8
}
$plan = [ordered]@{project=$ProjectId; region=$Region; status='prepared, not applied'; gateway="projects/$ProjectId/locations/$Region/agentGateways/openclass-egress"; armor="projects/$ProjectId/locations/$Region/templates/openclass"}
$plan | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $configRoot 'plan.json') -Encoding UTF8
Write-Host "Prepared configuration for $ProjectId / $Region in $configRoot"
if (-not $Apply) { Write-Host 'No cloud resources changed. Use -Apply from an authenticated gcloud terminal to provision base resources.'; return }
if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) { throw 'gcloud is not available. Install Google Cloud CLI and authenticate first.' }
function Run-Gcloud {
    param([string[]]$Arguments)
    & gcloud @Arguments
    if ($LASTEXITCODE -ne 0) { throw "gcloud operation failed: $($Arguments[0..([Math]::Min(2,$Arguments.Length-1))] -join ' ')" }
}
$account = & gcloud auth list --filter=status:ACTIVE --format=value(account)
if ($LASTEXITCODE -ne 0 -or -not $account) { throw 'Run gcloud auth login before provisioning.' }
Run-Gcloud @('projects','describe',$ProjectId,'--format=value(projectId)')
$billing = & gcloud billing projects describe $ProjectId --format=value(billingEnabled)
if ($LASTEXITCODE -ne 0 -or "$billing" -ne 'True') { throw 'Project billing is not enabled or cannot be verified.' }
$services = @('aiplatform.googleapis.com','agentidentity.googleapis.com','agentregistry.googleapis.com','networkservices.googleapis.com','networksecurity.googleapis.com','iap.googleapis.com','compute.googleapis.com','iam.googleapis.com','modelarmor.googleapis.com','run.googleapis.com','artifactregistry.googleapis.com','cloudbuild.googleapis.com','secretmanager.googleapis.com','logging.googleapis.com','monitoring.googleapis.com','serviceusage.googleapis.com')
Run-Gcloud (@('services','enable') + $services + @("--project=$ProjectId",'--quiet'))
& gcloud artifacts repositories describe openclass "--project=$ProjectId" "--location=$Region" --format=value(name) 2>$null
if ($LASTEXITCODE -ne 0) { Run-Gcloud @('artifacts','repositories','create','openclass','--repository-format=docker',"--project=$ProjectId","--location=$Region",'--quiet') }
foreach ($name in @('openclass-api','openclass-mcp')) {
    & gcloud iam service-accounts describe "$name@$ProjectId.iam.gserviceaccount.com" "--project=$ProjectId" --format=value(email) 2>$null
    if ($LASTEXITCODE -ne 0) { Run-Gcloud @('iam','service-accounts','create',$name,"--project=$ProjectId",'--quiet') }
}
# Template creation uses a structured JSON file; access tokens are never printed or persisted.
$accessToken = (& gcloud auth print-access-token).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Could not obtain Google Cloud access token' }
$headers = @{Authorization="Bearer $accessToken"}
$armorRoot = "https://modelarmor.$Region.rep.googleapis.com/v1/projects/$ProjectId/locations/$Region/templates"
$exists = $false
try { Invoke-RestMethod -Uri "$armorRoot/openclass" -Headers $headers -Method Get | Out-Null; $exists=$true }
catch { if ([int]$_.Exception.Response.StatusCode -ne 404) { throw } }
if (-not $exists) { Invoke-RestMethod -Uri "${armorRoot}?template_id=openclass" -Headers $headers -Method Post -ContentType 'application/json' -Body (Get-Content -LiteralPath (Join-Path $PSScriptRoot 'model-armor-template.json') -Raw) | Out-Null }
$accessToken=$null; $headers=$null
Run-Gcloud @('network-services','agent-gateways','import','openclass-egress',"--source=$(Join-Path $configRoot 'egress.yaml')","--project=$ProjectId","--location=$Region",'--quiet')
Run-Gcloud @('beta','service-extensions','authz-extensions','import','openclass-iap',"--source=$(Join-Path $configRoot 'iap-extension.yaml')","--project=$ProjectId","--location=$Region",'--quiet')
Run-Gcloud @('network-security','authz-policies','import','openclass-agent-access',"--source=$(Join-Path $configRoot 'iap-policy.yaml')","--project=$ProjectId","--location=$Region",'--quiet')
Run-Gcloud @('beta','service-extensions','authz-extensions','import','openclass-model-armor',"--source=$(Join-Path $configRoot 'armor-extension.yaml')","--project=$ProjectId","--location=$Region",'--quiet')
Run-Gcloud @('network-security','authz-policies','import','openclass-content-protection',"--source=$(Join-Path $configRoot 'armor-policy.yaml')","--project=$ProjectId","--location=$Region",'--quiet')
$number = (& gcloud projects describe $ProjectId --format=value(projectNumber)).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot read project number' }
$gatewayAgent = "serviceAccount:service-$number@gcp-sa-dep.iam.gserviceaccount.com"
foreach ($role in @('roles/modelarmor.calloutUser','roles/serviceusage.serviceUsageConsumer','roles/modelarmor.user')) {
    Run-Gcloud @('projects','add-iam-policy-binding',$ProjectId,"--member=$gatewayAgent","--role=$role",'--condition=None','--quiet')
}
$plan.status = 'base resources applied; workload deployment and verification still pending'
$plan | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $configRoot 'plan.json') -Encoding UTF8
Write-Host 'Base resources configured. Next: create-memory-bank.py, cloud database/secrets, MCP deployment, Agent Identity runtime, destination IAM, and negative-access verification.'
