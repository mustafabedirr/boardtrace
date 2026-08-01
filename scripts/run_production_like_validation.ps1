param(
    [ValidatePattern('^[a-z0-9][a-z0-9._-]{7,127}$')]
    [string]$RunId = ("bt-production-like-{0}" -f (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ"))
)

$ErrorActionPreference = "Stop"

$compose = "infrastructure/production-like/compose.yaml"

Write-Output "RUN_ID=$RunId"

try {
    docker info --format "Server={{.ServerVersion}}; OSType={{.OSType}}"
    if ($LASTEXITCODE -ne 0) { throw "docker info failed" }
    docker compose -f $compose config --quiet
    if ($LASTEXITCODE -ne 0) { throw "docker compose config failed" }
    docker compose -f $compose up --build --wait
    if ($LASTEXITCODE -ne 0) { throw "docker compose up failed" }
    $healthJson = docker compose -f $compose exec -T caddy wget -qO- http://127.0.0.1:8080/health
    if ($LASTEXITCODE -ne 0) { throw "Caddy-to-API health request failed" }
    $health = $healthJson | ConvertFrom-Json
    if ($health.status -ne "ok") {
        throw "minimum health response was not ok"
    }
    $readyJson = docker compose -f $compose exec -T caddy wget -qO- "--header=Authorization: Bearer production-like-probe" http://127.0.0.1:8080/api/v1/health/ready
    if ($LASTEXITCODE -ne 0) { throw "authenticated API readiness request failed" }
    $ready = $readyJson | ConvertFrom-Json
    if ($ready.status -ne "ready" -or $ready.checks.database -ne "ok") {
        throw "API-to-PostgreSQL readiness failed"
    }
    docker compose -f $compose exec -T postgres pg_isready -U runtime -d boardtrace
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL readiness failed" }
    docker compose -f $compose exec -T redis redis-cli ping
    if ($LASTEXITCODE -ne 0) { throw "Redis readiness failed" }
    docker compose -f $compose exec -T api alembic -c alembic.ini current
    if ($LASTEXITCODE -ne 0) { throw "Alembic current failed" }
    $taskId = (docker compose -f $compose exec -T api celery -A boardtrace_api.worker.celery_app call boardtrace.analysis.publish-outbox).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $taskId) { throw "queue probe submission failed" }
    $taskObserved = $false
    for ($attempt = 0; $attempt -lt 10; $attempt++) {
        $workerLogs = docker compose -f $compose logs --no-color worker
        if ($workerLogs -match [regex]::Escape($taskId) -and $workerLogs -match "succeeded") {
            $taskObserved = $true
            break
        }
        Start-Sleep -Seconds 1
    }
    if (-not $taskObserved) { throw "worker did not complete the queue probe" }
    docker compose -f $compose exec -T api python /app/scripts/validate_queue_lifecycle.py
    if ($LASTEXITCODE -ne 0) { throw "bounded FIFO queue lifecycle validation failed" }
    docker compose -f $compose stop worker
    if ($LASTEXITCODE -ne 0) { throw "worker pause for admission integration failed" }
    docker compose -f $compose exec -T api python /app/scripts/validate_integrated_admission_lifecycle.py
    if ($LASTEXITCODE -ne 0) { throw "integrated admission lifecycle validation failed" }
    docker compose -f $compose up -d --wait worker
    if ($LASTEXITCODE -ne 0) { throw "worker recovery after admission validation failed" }
    docker compose -f $compose stop redis
    if ($LASTEXITCODE -ne 0) { throw "Redis stop failed" }
    docker compose -f $compose exec -T api python /app/scripts/validate_redis_fail_closed.py
    if ($LASTEXITCODE -ne 0) { throw "Redis-unavailable fail-closed validation failed" }
    docker compose -f $compose up -d --wait redis
    if ($LASTEXITCODE -ne 0) { throw "Redis recovery failed" }
    docker compose -f $compose --profile disaster-recovery up --build --wait minio restore-postgres
    if ($LASTEXITCODE -ne 0) { throw "disaster-recovery dependencies failed" }
    docker compose -f $compose --profile disaster-recovery build backup
    if ($LASTEXITCODE -ne 0) { throw "backup image build failed" }
    docker compose -f $compose --profile disaster-recovery run --rm --no-deps backup
    if ($LASTEXITCODE -ne 0) { throw "encrypted backup and restore validation failed" }
    docker compose -f $compose ps
    if ($LASTEXITCODE -ne 0) { throw "docker compose ps failed" }
    Write-Output "VALIDATION_RESULT=PASS"
}
finally {
    docker compose -f $compose --profile disaster-recovery down --volumes --remove-orphans
    if ($LASTEXITCODE -ne 0) { Write-Warning "Docker cleanup failed" }
}
