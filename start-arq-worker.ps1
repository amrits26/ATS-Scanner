# PowerShell script to start ARQ worker for local development
# Usage: .\start-arq-worker.ps1

Write-Host "[*] Starting ARQ worker..." -ForegroundColor Cyan

# Check if virtual environment is activated
if (-not (Test-Path ".\.venv\Scripts\activate.ps1")) {
    Write-Host "[X] Virtual environment not found." -ForegroundColor Red
    Write-Host "   Create one with: python -m venv .venv" -ForegroundColor Gray
    exit 1
}

# Activate virtual environment
& ".\.venv\Scripts\Activate.ps1"

# Check if Redis is running
Write-Host "Checking Redis connection..." -ForegroundColor Yellow
$redisTest = redis-cli -p 6379 ping 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[X] Redis is not running on port 6379" -ForegroundColor Red
    Write-Host "   Start Redis with: .\start-redis.ps1" -ForegroundColor Gray
    exit 1
}
Write-Host "[OK] Redis is ready" -ForegroundColor Green

# Start ARQ worker
Write-Host "Starting worker..." -ForegroundColor Cyan
Write-Host "  Settings: backend.worker.WorkerSettings" -ForegroundColor Gray
Write-Host "  Redis: redis://localhost:6379/0" -ForegroundColor Gray
Write-Host "  Press Ctrl+C to stop" -ForegroundColor Gray

$env:REDIS_URL = "redis://localhost:6379/0"
python -m arq backend.worker.WorkerSettings

if ($LASTEXITCODE -ne 0) {
    Write-Host "[X] ARQ worker failed to start" -ForegroundColor Red
    exit 1
}
