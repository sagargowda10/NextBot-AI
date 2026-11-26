# NextBot AI - full local verification on Windows (PowerShell).
# Runs: backend lint + type-check + unit + integration tests, frontend type-check + lint + build, Playwright E2E.
# Writes everything to docs\test-results-local.md so the README can quote REAL results.
#
# Usage (from the NextBot-AI folder, with the dev stack running for E2E):
#   docker compose -f docker-compose.dev.yml up -d --build
#   powershell -ExecutionPolicy Bypass -File .\scripts\verify.ps1
#   (add -SkipE2E to skip browser tests)
param([switch]$SkipE2E)

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$out = Join-Path $root "docs\test-results-local.md"
$results = @()

function Step($name, $dir, [scriptblock]$cmd) {
    Write-Host "`n=== $name ===" -ForegroundColor Cyan
    Push-Location $dir
    $log = & $cmd 2>&1 | Out-String
    $code = $LASTEXITCODE
    Pop-Location
    Write-Host $log
    $status = if ($code -eq 0) { "PASS" } else { "FAIL (exit $code)" }
    Write-Host "--> $status" -ForegroundColor ($(if ($code -eq 0) { "Green" } else { "Red" }))
    $tail = ($log -split "`n" | Where-Object { $_.Trim() } | Select-Object -Last 40) -join "`n"
    $script:results += [pscustomobject]@{ Step = $name; Status = $status; Tail = $tail }
}

$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$py = Join-Path $backend ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "Creating backend\.venv ..." -ForegroundColor Yellow
    Push-Location $backend; py -3.12 -m venv .venv; Pop-Location
}

Step "Backend: install dev requirements" $backend { & $py -m pip install -q -r requirements-dev.txt }
Step "Backend: ruff lint"               $backend { & $py -m ruff check app tests }
Step "Backend: mypy type-check"         $backend { & $py -m mypy app }
Step "Backend: unit tests"              $backend { & $py -m pytest tests/unit -q -rfE }
Step "Backend: integration tests (API + SQLite; Postgres concurrency via Testcontainers/Docker)" $backend { & $py -m pytest tests/integration -q -rfEs }
Step "Backend: Alembic migrations"      $backend { $env:DATABASE_URL = "sqlite+aiosqlite:///./verify.db"; & $py -m alembic upgrade head; Remove-Item -ErrorAction SilentlyContinue verify.db; Remove-Item Env:DATABASE_URL }

Step "Frontend: npm install"            $frontend { npm install --no-audit --no-fund }
Step "Frontend: TypeScript type-check"  $frontend { npm run typecheck }
Step "Frontend: lint"                   $frontend { npm run lint }
Step "Frontend: production build"       $frontend { npm run build }

if (-not $SkipE2E) {
    Step "E2E: Playwright (needs stack on :3000/:8000)" $frontend {
        npx playwright install chromium
        $env:E2E_NO_SERVER = "1"; npx playwright test --reporter=line; Remove-Item Env:E2E_NO_SERVER
    }
}

$pyver = & $py --version 2>&1
$nodever = node --version 2>&1
$lines = @("# Local verification results", "",
    "Run on: $(Get-Date -Format 'yyyy-MM-dd HH:mm') | Windows | $pyver | Node $nodever", "",
    "| Step | Result |", "|---|---|")
foreach ($r in $results) { $lines += "| $($r.Step) | $($r.Status) |" }
$lines += ""
foreach ($r in $results) { $lines += "### $($r.Step) - $($r.Status)"; $lines += '```'; $lines += $r.Tail; $lines += '```'; $lines += "" }
$lines | Set-Content -Encoding UTF8 $out
Write-Host "`nSaved results to $out" -ForegroundColor Green
$results | Format-Table Step, Status -AutoSize
