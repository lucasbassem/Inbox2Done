$ErrorActionPreference = "Stop"

if (-not (Test-Path ".env.docker")) {
    throw "Missing .env.docker. Copy .env.docker.example to .env.docker first."
}

Write-Host "Validating Docker Compose configuration..."
docker compose --env-file .env.docker config --quiet

Write-Host "Building and starting infrastructure..."
docker compose --env-file .env.docker up -d --build

Write-Host "Waiting for the API readiness endpoint..."
$attempts = 30

for ($attempt = 1; $attempt -le $attempts; $attempt++) {
    try {
        $health = Invoke-RestMethod `
            -Uri "http://localhost:8000/health/ready" `
            -TimeoutSec 3

        if ($health.status -eq "ok") {
            Write-Host "API is ready and PostgreSQL is connected."
            break
        }
    }
    catch {
        if ($attempt -eq $attempts) {
            docker compose --env-file .env.docker ps
            docker compose --env-file .env.docker logs api migrate worker
            throw "Docker stack did not become ready."
        }

        Start-Sleep -Seconds 2
    }
}

Write-Host "Checking Celery worker connectivity..."
docker compose --env-file .env.docker exec -T worker `
    celery -A app.worker.celery_app:celery_app inspect ping --timeout=10

Write-Host "Current service state:"
docker compose --env-file .env.docker ps

Write-Host ""
Write-Host "Scale workers with:"
Write-Host "docker compose --env-file .env.docker up -d --scale worker=3"
