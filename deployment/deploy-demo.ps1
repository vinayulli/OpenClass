param([switch]$Apply)
$ErrorActionPreference = 'Stop'
$projectId = 'hackathon-506016'
$region = 'us-central1'
$service = 'openclass-demo'
$account = "openclass-web@$projectId.iam.gserviceaccount.com"
$revisionTag = Get-Date -Format 'yyyyMMdd-HHmmss'
$image = "$region-docker.pkg.dev/$projectId/openclass/web:$revisionTag"
Write-Host "Target: public synthetic demo $service in $projectId / $region"
Write-Host "Image: $image; one always-on API instance with Cloud SQL and server-side secrets."
if (-not $Apply) { Write-Host 'No changes. Use -Apply after the local checks and secret setup in public-demo.md.'; return }
Set-Location (Split-Path $PSScriptRoot -Parent)
function Invoke-Gcloud {
    param([string[]]$Arguments)
    & gcloud @Arguments
    if ($LASTEXITCODE -ne 0) { throw "gcloud failed: $($Arguments[0..([Math]::Min(2,$Arguments.Length-1))] -join ' ')" }
}
Invoke-Gcloud @('services','enable','run.googleapis.com','cloudbuild.googleapis.com','artifactregistry.googleapis.com','sqladmin.googleapis.com','secretmanager.googleapis.com',"--project=$projectId",'--quiet')
& gcloud artifacts repositories describe openclass "--project=$projectId" "--location=$region" '--format=value(name)' 2>$null
if ($LASTEXITCODE -ne 0) { Invoke-Gcloud @('artifacts','repositories','create','openclass','--repository-format=docker',"--project=$projectId","--location=$region",'--quiet') }
& gcloud iam service-accounts describe $account "--project=$projectId" '--format=value(email)' 2>$null
if ($LASTEXITCODE -ne 0) { Invoke-Gcloud @('iam','service-accounts','create','openclass-web',"--project=$projectId",'--quiet') }
foreach ($name in @('openclass-db-password','openclass-gemini-api-key')) {
    Invoke-Gcloud @('secrets','describe',$name,"--project=$projectId",'--format=value(name)')
    Invoke-Gcloud @('secrets','add-iam-policy-binding',$name,"--project=$projectId","--member=serviceAccount:$account",'--role=roles/secretmanager.secretAccessor','--quiet')
}
Invoke-Gcloud @('projects','add-iam-policy-binding',$projectId,"--member=serviceAccount:$account",'--role=roles/cloudsql.client','--condition=None','--quiet')
Invoke-Gcloud @('builds','submit','.',"--tag=$image","--project=$projectId",'--quiet')
Invoke-Gcloud @('run','deploy',$service,"--image=$image","--project=$projectId","--region=$region","--service-account=$account",'--port=8080',"--add-cloudsql-instances=${projectId}:${region}:openclass-postgres","--env-vars-file=$PSScriptRoot/cloud-run-demo.env.yaml",'--set-secrets=DB_PASSWORD=openclass-db-password:latest,GEMINI_API_KEY=openclass-gemini-api-key:latest','--min-instances=1','--max-instances=1','--no-cpu-throttling','--memory=2Gi','--cpu=1','--timeout=300','--concurrency=20','--allow-unauthenticated','--quiet')
Invoke-Gcloud @('run','services','describe',$service,"--project=$projectId","--region=$region",'--format=value(status.url)')
Write-Host 'Deployment requested. Verify health, login, exam publication/attempts and learner isolation before sharing the URL.'
