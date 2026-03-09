# IntelliResume AI - Backend Startup Script
# This script starts the FastAPI backend server

Write-Host "================================" -ForegroundColor Cyan
Write-Host "IntelliResume AI - Backend Start" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

# Check Python installation
Write-Host "[1/4] Checking Python installation..." -ForegroundColor Yellow
$pythonPath = (Get-Command python -ErrorAction SilentlyContinue).Path
if (-not $pythonPath) {
    Write-Host "ERROR: Python not found in PATH" -ForegroundColor Red
    exit 1
}
Write-Host "✓ Python found: $pythonPath" -ForegroundColor Green
Write-Host ""

# Check if we're in the correct directory
Write-Host "[2/4] Checking project structure..." -ForegroundColor Yellow
if (-not (Test-Path ".\backend\main.py")) {
    Write-Host "ERROR: backend/main.py not found. Please run from project root directory." -ForegroundColor Red
    exit 1
}
Write-Host "✓ Project structure valid" -ForegroundColor Green
Write-Host ""

# Check if required packages are installed
Write-Host "[3/4] Checking required dependencies..." -ForegroundColor Yellow
$packages = @("fastapi", "uvicorn", "python-multipart", "pdfplumber", "python-docx", "openai", "scikit-learn", "matplotlib", "pydantic")
foreach ($pkg in $packages) {
    try {
        python -c "import $($pkg.Replace('-', '_'))" 2>$null
        if ($?) {
            Write-Host "✓ $pkg installed" -ForegroundColor Green
        } else {
            Write-Host "✗ $pkg NOT installed" -ForegroundColor Red
        }
    } catch {
        Write-Host "✗ $pkg NOT installed" -ForegroundColor Red
    }
}
Write-Host ""

# Check if .env file exists and has API key
Write-Host "[4/4] Configuration check..." -ForegroundColor Yellow
if (Test-Path ".\.env") {
    $envContent = Get-Content ".\.env"
    if ($envContent -like "*your_openai_api_key_here*") {
        Write-Host "⚠ WARNING: OPENAI_API_KEY is not set in .env file" -ForegroundColor Yellow
        Write-Host "The server will start but analysis features will fail without a valid API key." -ForegroundColor Yellow
        Write-Host "Update .env with your OpenAI API key before running analysis." -ForegroundColor Yellow
    } else {
        Write-Host "✓ .env file configured" -ForegroundColor Green
    }
} else {
    Write-Host "⚠ WARNING: .env file not found" -ForegroundColor Yellow
}
Write-Host ""

# Start the server
Write-Host "Starting FastAPI server..." -ForegroundColor Cyan
Write-Host "Server will run at: http://127.0.0.1:8000" -ForegroundColor Cyan
Write-Host "API docs available at: http://127.0.0.1:8000/docs" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Yellow
Write-Host ""

# Start uvicorn with proper error handling
& python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERROR: Backend failed to start" -ForegroundColor Red
    Write-Host "Exit code: $LASTEXITCODE" -ForegroundColor Red
    Write-Host ""
    Write-Host "Troubleshooting steps:" -ForegroundColor Yellow
    Write-Host "1. Verify Python packages: pip install -r requirements.txt" -ForegroundColor White
    Write-Host "2. Check backend/main.py for syntax errors" -ForegroundColor White
    Write-Host "3. Ensure you're in the project root directory" -ForegroundColor White
    Write-Host "4. Check .env file configuration" -ForegroundColor White
    exit 1
}
