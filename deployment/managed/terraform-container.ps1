param(
    [string]$Directory = 'deployment/managed',
    [Parameter(ValueFromRemainingArguments=$true)][string[]]$TerraformArguments
)
$ErrorActionPreference = 'Stop'
$workspacePath = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$configPath = (Resolve-Path (Join-Path $workspacePath $Directory)).Path
if (-not $configPath.StartsWith($workspacePath+[IO.Path]::DirectorySeparatorChar)) { throw 'Terraform directory must be inside OpenClass' }
$adcPath = if ($env:GOOGLE_APPLICATION_CREDENTIALS) { $env:GOOGLE_APPLICATION_CREDENTIALS } else { Join-Path $env:APPDATA 'gcloud/application_default_credentials.json' }
if (-not (Test-Path -LiteralPath $adcPath)) { throw 'Application Default Credentials are missing' }
$relativePath = $configPath.Substring($workspacePath.Length).Replace('\','/')
& docker run --rm --mount "type=bind,source=$workspacePath,target=/work" --mount "type=bind,source=$adcPath,target=/credentials/adc.json,readonly" -e GOOGLE_APPLICATION_CREDENTIALS=/credentials/adc.json -e GOOGLE_CLOUD_QUOTA_PROJECT=hackathon-506016 -w "/work$relativePath" hashicorp/terraform:1.13 @TerraformArguments
if ($LASTEXITCODE -ne 0) { throw 'Terraform command failed; no credentials were printed by this wrapper' }
