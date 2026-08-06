param(
    [string]$ClusterName = "inbox2done",
    [string]$Namespace = "inbox2done",
    [string]$EnvironmentFile = ".env.docker",
    [string]$Image = "inbox2done-backend:k8s"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$environmentPath = Join-Path $repoRoot $EnvironmentFile
$expectedContext = "kind-$ClusterName"

function Read-DotEnv {
    param([Parameter(Mandatory)][string]$Path)
    $values = @{}
    foreach ($rawLine in Get-Content -Path $Path) {
        $line = $rawLine.Trim()
        if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith("#")) { continue }
        $separator = $line.IndexOf("=")
        if ($separator -le 0) { continue }
        $name = $line.Substring(0, $separator).Trim()
        $value = $line.Substring($separator + 1).Trim()
        if ($value.Length -ge 2 -and ((($value.StartsWith('"')) -and $value.EndsWith('"')) -or (($value.StartsWith("'")) -and $value.EndsWith("'")))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        $values[$name] = $value
    }
    return $values
}

function Get-EnvironmentValue {
    param([hashtable]$Values, [string]$Name, [string]$Default = "")
    if ($Values.ContainsKey($Name) -and -not [string]::IsNullOrWhiteSpace($Values[$Name])) { return $Values[$Name] }
    return $Default
}

function Invoke-Checked {
    param([Parameter(Mandatory)][string]$Executable, [Parameter(ValueFromRemainingArguments)][string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Executable failed with exit code $LASTEXITCODE." }
}

if (-not (Test-Path $environmentPath)) { throw "Missing $environmentPath. Copy .env.docker.example to .env.docker first." }
$currentContext = (& kubectl config current-context).Trim()
if ($currentContext -ne $expectedContext) { throw "Current context is '$currentContext'; expected '$expectedContext'." }

$environment = Read-DotEnv -Path $environmentPath
$postgresUser = Get-EnvironmentValue $environment "POSTGRES_USER" "inbox2done"
$postgresPassword = Get-EnvironmentValue $environment "POSTGRES_PASSWORD" "inbox2done_dev"
$postgresDatabase = Get-EnvironmentValue $environment "POSTGRES_DB" "inbox2done"
$sessionSecret = Get-EnvironmentValue $environment "SESSION_SECRET_KEY"

if ([string]::IsNullOrWhiteSpace($sessionSecret) -or $sessionSecret -eq "replace-with-a-long-random-development-secret") {
    $bytes = New-Object byte[] 48
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()

try {
    $rng.GetBytes($bytes)
}
finally {
    $rng.Dispose()
}

$sessionSecret = [Convert]::ToBase64String($bytes)
    Write-Warning "Generated a temporary Kubernetes session secret because .env.docker contained no usable value."
}

$databaseUrl = "postgresql+psycopg://$([Uri]::EscapeDataString($postgresUser)):$([Uri]::EscapeDataString($postgresPassword))@postgres:5432/$([Uri]::EscapeDataString($postgresDatabase))"

Write-Host "Building and loading $Image..."
Invoke-Checked docker build -t $Image (Join-Path $repoRoot "backend")
Invoke-Checked kind load docker-image $Image --name $ClusterName

Invoke-Checked kubectl apply -f (Join-Path $repoRoot "k8s\namespace.yaml")

$secretArguments = @(
    "create", "secret", "generic", "inbox2done-secrets", "--namespace", $Namespace,
    "--from-literal=POSTGRES_USER=$postgresUser",
    "--from-literal=POSTGRES_PASSWORD=$postgresPassword",
    "--from-literal=POSTGRES_DB=$postgresDatabase",
    "--from-literal=SESSION_SECRET_KEY=$sessionSecret",
    "--from-literal=DATABASE_URL=$databaseUrl",
    "--dry-run=client", "-o", "yaml"
)

$optional = @{
    OPENAI_API_KEY = Get-EnvironmentValue $environment "OPENAI_API_KEY"
    GOOGLE_CLIENT_ID = Get-EnvironmentValue $environment "GOOGLE_CLIENT_ID"
    GOOGLE_CLIENT_SECRET = Get-EnvironmentValue $environment "GOOGLE_CLIENT_SECRET"
}
foreach ($entry in $optional.GetEnumerator()) {
    if (-not [string]::IsNullOrWhiteSpace($entry.Value)) { $secretArguments += "--from-literal=$($entry.Key)=$($entry.Value)" }
}

$secretYaml = & kubectl @secretArguments
if ($LASTEXITCODE -ne 0) { throw "Failed to render the Kubernetes Secret." }
$secretYaml | & kubectl apply -f -
if ($LASTEXITCODE -ne 0) { throw "Failed to apply the Kubernetes Secret." }

Invoke-Checked kubectl apply -f (Join-Path $repoRoot "k8s\configmap.yaml")
Invoke-Checked kubectl apply -f (Join-Path $repoRoot "k8s\postgres.yaml")
Invoke-Checked kubectl apply -f (Join-Path $repoRoot "k8s\redis.yaml")
Invoke-Checked kubectl rollout status statefulset/postgres -n $Namespace --timeout=180s
Invoke-Checked kubectl rollout status statefulset/redis -n $Namespace --timeout=180s

& kubectl delete job inbox2done-migrate -n $Namespace --ignore-not-found | Out-Null
Invoke-Checked kubectl apply -f (Join-Path $repoRoot "k8s\migration-job.yaml")
& kubectl wait --for=condition=complete job/inbox2done-migrate -n $Namespace --timeout=180s
if ($LASTEXITCODE -ne 0) {
    & kubectl logs job/inbox2done-migrate -n $Namespace --all-containers=true
    throw "The migration Job did not complete."
}

Invoke-Checked kubectl apply -f (Join-Path $repoRoot "k8s\api.yaml")
Invoke-Checked kubectl apply -f (Join-Path $repoRoot "k8s\worker.yaml")
Invoke-Checked kubectl rollout status deployment/inbox2done-api -n $Namespace --timeout=240s
Invoke-Checked kubectl rollout status deployment/inbox2done-worker -n $Namespace --timeout=240s

Write-Host ""
Write-Host "Inbox2Done is deployed to Kubernetes."
& kubectl get pods,services,persistentvolumeclaims,jobs -n $Namespace
Write-Host ""
Write-Host "Run: kubectl port-forward service/inbox2done-api 8000:80 -n $Namespace"
