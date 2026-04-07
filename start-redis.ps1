# PowerShell script to start Redis for development
# Usage: .\start-redis.ps1

Write-Host "[*] Starting Redis container for local development..." -ForegroundColor Cyan

# Check if Docker is running
$dockerStatus = docker ps --format "table" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[X] Docker is not running. Please start Docker Desktop and try again." -ForegroundColor Red
    exit 1
}

# Check if redis container is already running
$existingRedis = docker ps --filter "name=intelliresume_redis_dev" --format "{{.ID}}"
if ($existingRedis) {
    Write-Host "[OK] Redis container is already running (ID: $existingRedis)" -ForegroundColor Green
    Write-Host "  Connect with: redis-cli -p 6379" -ForegroundColor Gray
    exit 0
}

# Stop and remove old container if exists
$oldRedis = docker ps -a --filter "name=intelliresume_redis_dev" --format "{{.ID}}"
if ($oldRedis) {
    Write-Host "Cleaning up old Redis container..." -ForegroundColor Yellow
    docker rm -f $oldRedis | Out-Null
}

# Start Redis from docker-compose
docker-compose -f docker-compose.dev.yml up -d redis

if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Redis started successfully!" -ForegroundColor Green
    Write-Host "  Port: 6379" -ForegroundColor Gray
    Write-Host "  Connect with: redis-cli -p 6379" -ForegroundColor Gray
    Write-Host "  Logs: docker-compose -f docker-compose.dev.yml logs redis" -ForegroundColor Gray
    Start-Sleep -Seconds 2
    
    # Try to connect
    $redisTest = redis-cli -p 6379 ping 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] Redis is ready (ping: $redisTest)" -ForegroundColor Green
    } else {
        Write-Host "  [!] Redis may not be ready yet. Try 'redis-cli ping' in a few seconds." -ForegroundColor Yellow
    }
} else {
    Write-Host "[X] Failed to start Redis" -ForegroundColor Red
    exit 1
}
