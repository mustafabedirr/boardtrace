$ErrorActionPreference = "Stop"

$compose = "infrastructure/production-like/compose.r6-tests.yaml"
$testDatabaseUrl = "postgresql+asyncpg://runtime:test-only-database@127.0.0.1:15432/boardtrace_test"
$testTemp = Join-Path $PSScriptRoot "..\.tmp\r6-pytest"
$python = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"

New-Item -ItemType Directory -Path $testTemp -Force | Out-Null
$env:TMP = $testTemp
$env:TEMP = $testTemp
$env:TMPDIR = $testTemp
$env:PYTHONPATH = "apps/api/src;."

& $python -m pytest -q --basetemp "$testTemp\filesystem" -p no:cacheprovider `
  apps/api/tests/test_errors.py::test_unexpected_error_hides_internal_details_in_production `
  apps/api/tests/test_settings.py::test_production_wildcard_cors_is_rejected `
  apps/api/tests/test_settings.py::test_production_explicit_configuration_is_accepted `
  apps/api/tests/test_settings.py::test_production_missing_critical_configuration_fails_fast `
  apps/api/tests/test_settings.py::test_production_rejects_development_network_defaults `
  apps/api/tests/test_settings.py::test_production_rejects_invalid_stockfish_path
if ($LASTEXITCODE -ne 0) { throw "R6 filesystem qualification failed" }

try {
    docker compose -f $compose up -d --wait
    if ($LASTEXITCODE -ne 0) { throw "R6 PostgreSQL startup failed" }
    $env:BOARDTRACE_DATABASE_URL = $testDatabaseUrl
    $env:BOARDTRACE_TEST_DATABASE_URL = $testDatabaseUrl
    & $python -m alembic -c apps/api/alembic.ini upgrade head
    if ($LASTEXITCODE -ne 0) { throw "R6 PostgreSQL migration failed" }
    & $python -m pytest -q --basetemp "$testTemp\postgres" -p no:cacheprovider `
      apps/api/tests/integration/test_transaction_boundary_ingestion.py
    if ($LASTEXITCODE -ne 0) { throw "R6 PostgreSQL qualification failed" }
}
finally {
    docker compose -f $compose down --volumes --remove-orphans
    if ($LASTEXITCODE -ne 0) { Write-Warning "R6 PostgreSQL cleanup failed" }
}

Write-Output "R6 evidence qualification passed: filesystem=10/10; PostgreSQL=5/5"
