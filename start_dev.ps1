# Sortify One-Click Start Script
# This script starts both Backend (FastAPI + uv) and Frontend (React + npm)

Write-Host "Starting Sortify Development Environment..." -ForegroundColor Cyan

# Get current script directory
$RootPath = $PSScriptRoot

# --- Start Backend ---
$BackendPath = Join-Path $RootPath "backend"
if (Test-Path $BackendPath) {
    Write-Host "Starting Backend..." -ForegroundColor Green
    # Start new PowerShell window for backend
    Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command", "cd '$BackendPath'; Write-Host 'Starting FastAPI (uv)...' -ForegroundColor Yellow; uv run uvicorn app.main:app --reload"
} else {
    Write-Host "Backend directory not found: $BackendPath" -ForegroundColor Red
}

# --- Start Frontend ---
$FrontendPath = Join-Path $RootPath "frontend"
if (Test-Path $FrontendPath) {
    Write-Host "Starting Frontend..." -ForegroundColor Green
    # Start new PowerShell window for frontend
    Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command", "cd '$FrontendPath'; Write-Host 'Starting React (npm)...' -ForegroundColor Yellow; npm start"
} else {
    Write-Host "Frontend directory not found: $FrontendPath" -ForegroundColor Red
}

Write-Host "Services started! Please check the new windows." -ForegroundColor Cyan
