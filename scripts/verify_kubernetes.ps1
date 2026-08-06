param(
    [string]$Namespace = "inbox2done",
    [switch]$SkipScalingProof
)

$ErrorActionPreference = "Stop"

function Assert-NativeSuccess {
    param(
        [Parameter(Mandatory)]
        [string]$Operation
    )

    if ($LASTEXITCODE -ne 0) {
        throw "$Operation failed with exit code $LASTEXITCODE."
    }
}

function Invoke-Kubectl {
    param(
        [Parameter(ValueFromRemainingArguments)]
        [string[]]$Arguments
    )

    & kubectl @Arguments
    Assert-NativeSuccess -Operation "kubectl $($Arguments -join ' ')"
}

Write-Host "Checking PostgreSQL rollout..."
Invoke-Kubectl rollout status `
    statefulset/postgres `
    -n $Namespace `
    --timeout=240s

Write-Host "Checking Redis rollout..."
Invoke-Kubectl rollout status `
    statefulset/redis `
    -n $Namespace `
    --timeout=240s

Write-Host "Checking API rollout..."
Invoke-Kubectl rollout status `
    deployment/inbox2done-api `
    -n $Namespace `
    --timeout=240s

Write-Host "Checking worker rollout..."
Invoke-Kubectl rollout status `
    deployment/inbox2done-worker `
    -n $Namespace `
    --timeout=240s

Write-Host ""
Write-Host "Current Kubernetes resources:"

& kubectl get `
    pods,services,persistentvolumeclaims,jobs `
    -n $Namespace `
    -o wide

Assert-NativeSuccess -Operation "kubectl get application resources"

$apiPod = (
    & kubectl get pods `
        -n $Namespace `
        -l "app.kubernetes.io/component=api" `
        -o "jsonpath={.items[0].metadata.name}"
).Trim()

Assert-NativeSuccess -Operation "Find API Pod"

if ([string]::IsNullOrWhiteSpace($apiPod)) {
    throw "No API Pod was found."
}

Write-Host ""
Write-Host "Checking API readiness inside Pod $apiPod..."

& kubectl exec `
    -n $Namespace `
    $apiPod `
    -c api `
    -- `
    python `
    -c `
    "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=5).read().decode())"

Assert-NativeSuccess -Operation "API readiness verification"

$workerPod = (
    & kubectl get pods `
        -n $Namespace `
        -l "app.kubernetes.io/component=worker" `
        -o "jsonpath={.items[0].metadata.name}"
).Trim()

Assert-NativeSuccess -Operation "Find Celery worker Pod"

if ([string]::IsNullOrWhiteSpace($workerPod)) {
    throw "No Celery worker Pod was found."
}

Write-Host ""
Write-Host "Checking Celery worker $workerPod..."

& kubectl exec `
    -n $Namespace `
    $workerPod `
    -c worker `
    -- `
    sh `
    -c `
    'celery -A app.worker.celery_app:celery_app inspect ping -d "worker@$(hostname)" --timeout=10'

Assert-NativeSuccess -Operation "Celery worker ping"

if (-not $SkipScalingProof) {
    $originalReplicas = (
        & kubectl get deployment inbox2done-worker `
            -n $Namespace `
            -o "jsonpath={.spec.replicas}"
    ).Trim()

    Assert-NativeSuccess -Operation "Read current worker replica count"

    if ([string]::IsNullOrWhiteSpace($originalReplicas)) {
        $originalReplicas = "2"
    }

    try {
        Write-Host ""
        Write-Host "Scaling Celery workers from $originalReplicas to 3 replicas..."

        Invoke-Kubectl scale `
            deployment/inbox2done-worker `
            --replicas=3 `
            -n $Namespace

        Invoke-Kubectl rollout status `
            deployment/inbox2done-worker `
            -n $Namespace `
            --timeout=240s

        Write-Host ""
        Write-Host "Scaled worker Pods:"

        & kubectl get pods `
            -n $Namespace `
            -l "app.kubernetes.io/component=worker" `
            -o wide

        Assert-NativeSuccess -Operation "List scaled worker Pods"

        Write-Host ""
        Write-Host "Broadcasting a ping to all Celery workers..."

        $pingOutput = & kubectl exec `
            -n $Namespace `
            deployment/inbox2done-worker `
            -c worker `
            -- `
            celery `
            -A `
            app.worker.celery_app:celery_app `
            inspect `
            ping `
            --timeout=10 2>&1

        $pingText = $pingOutput -join [Environment]::NewLine
        Write-Host $pingText

        $pongCount = (
            [regex]::Matches(
                $pingText,
                "(?m)^\s*pong\s*$"
            )
        ).Count

        if ($pongCount -lt 3) {
            throw "Expected responses from 3 Celery workers, but received $pongCount pong responses."
        }

        Write-Host "Verified responses from $pongCount Celery workers."
    }
    finally {
        Write-Host ""
        Write-Host "Restoring worker Deployment to $originalReplicas replicas..."

        & kubectl scale `
            deployment/inbox2done-worker `
            --replicas=$originalReplicas `
            -n $Namespace | Out-Null

        if ($LASTEXITCODE -eq 0) {
            & kubectl rollout status `
                deployment/inbox2done-worker `
                -n $Namespace `
                --timeout=240s | Out-Null
        }
    }
}

Write-Host ""
Write-Host "Kubernetes verification passed."