# Start everything MeetMind needs, in order, and tell you the truth about what
# came up. Run this, open the URL, done.
#
#   .\start.ps1          start everything
#   .\start.ps1 -Stop    shut everything down
#   .\start.ps1 -Status  check what is running
#
# NOTE: keep this file pure ASCII. Windows PowerShell 5.1 decodes .ps1 as
# Windows-1252 unless there is a UTF-8 BOM, so smart quotes and em-dashes turn
# into mojibake or outright parse errors.

param(
    [switch]$Stop,
    [switch]$Status
)

$ErrorActionPreference = 'Continue'

$Root      = $PSScriptRoot
$Python    = Join-Path $Root '.venv\Scripts\python.exe'
$OllamaExe = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'

function Test-Port([int]$Port) {
    $c = New-Object Net.Sockets.TcpClient
    try {
        $c.Connect('127.0.0.1', $Port)
        return $true
    } catch {
        return $false
    } finally {
        $c.Dispose()
    }
}

function Write-Line([string]$Label, [bool]$Ok, [string]$Detail) {
    $mark  = if ($Ok) { '[ OK ]' } else { '[FAIL]' }
    $color = if ($Ok) { 'Green' } else { 'Red' }
    Write-Host $mark -ForegroundColor $color -NoNewline
    Write-Host "  $Label" -NoNewline
    if ($Detail) { Write-Host "  $Detail" -ForegroundColor DarkGray } else { Write-Host '' }
}

# ---------------------------------------------------------------- stop --------

if ($Stop) {
    Write-Host "`nStopping MeetMind..." -ForegroundColor Cyan

    Get-Process -Name node -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -like "*$Root*" -or $_.CommandLine -like '*vite*' } |
        Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Host '  frontend stopped'

    Get-Process -Name python -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -like "*$Root*" } |
        Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Host '  backend stopped'

    & (Join-Path $Root 'scripts\pg.ps1') stop

    Write-Host "`nOllama is left running - it is a shared service. Quit it from the system tray if you want it gone.`n" -ForegroundColor DarkGray
    exit 0
}

# -------------------------------------------------------------- status --------

if ($Status) {
    Write-Host "`nMeetMind status" -ForegroundColor Cyan
    Write-Host ('-' * 52)

    Write-Line 'PostgreSQL  :5433' (Test-Port 5433) ''
    Write-Line 'Ollama      :11434' (Test-Port 11434) ''
    Write-Line 'Backend API :8000' (Test-Port 8000) ''
    Write-Line 'Frontend    :5173' (Test-Port 5173) ''

    if (Test-Port 8000) {
        try {
            $h = Invoke-RestMethod 'http://127.0.0.1:8000/api/health' -TimeoutSec 5
            Write-Host ''
            Write-Host "  health: $($h.status)" -ForegroundColor $(if ($h.status -eq 'healthy') { 'Green' } else { 'Yellow' })
            if ($h.llm.detail) { Write-Host "  note:   $($h.llm.detail)" -ForegroundColor Yellow }
        } catch { }
    }
    Write-Host ''
    exit 0
}

# --------------------------------------------------------------- start --------

Write-Host "`nStarting MeetMind" -ForegroundColor Cyan
Write-Host ('-' * 52)

# Preflight: fail loudly and specifically rather than half-starting.
if (-not (Test-Path $Python)) {
    Write-Line 'Python venv' $false 'not found'
    Write-Host "`n  Run first:  python -m venv .venv" -ForegroundColor Yellow
    Write-Host "              .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt`n" -ForegroundColor Yellow
    exit 1
}
if (-not (Test-Path (Join-Path $Root '.env'))) {
    Write-Line '.env' $false 'not found'
    Write-Host "`n  Run first:  python scripts\bootstrap_env.py`n" -ForegroundColor Yellow
    exit 1
}

# --- PostgreSQL ---
if (Test-Port 5433) {
    Write-Line 'PostgreSQL' $true 'already running'
} else {
    & (Join-Path $Root 'scripts\pg.ps1') start | Out-Null
    Start-Sleep -Seconds 2
    Write-Line 'PostgreSQL' (Test-Port 5433) 'port 5433'
}

# --- Ollama ---
if (Test-Port 11434) {
    Write-Line 'Ollama' $true 'already running'
} elseif (Test-Path $OllamaExe) {
    Start-Process -FilePath $OllamaExe -ArgumentList 'serve' -WindowStyle Hidden
    # Give it a moment to bind; it is not instant on a cold start.
    for ($i = 0; $i -lt 15 -and -not (Test-Port 11434); $i++) { Start-Sleep -Seconds 1 }
    Write-Line 'Ollama' (Test-Port 11434) 'port 11434'
} else {
    Write-Line 'Ollama' $false 'not installed - get it from https://ollama.com'
}

# --- Backend ---
if (Test-Port 8000) {
    Write-Line 'Backend API' $true 'already running'
} else {
    $backendDir = Join-Path $Root 'backend'
    Start-Process -FilePath 'powershell' -WindowStyle Minimized -ArgumentList @(
        '-NoExit', '-Command',
        "Set-Location '$backendDir'; `$env:PYTHONPATH='$backendDir'; & '$Python' -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
    )
    for ($i = 0; $i -lt 30 -and -not (Test-Port 8000); $i++) { Start-Sleep -Seconds 1 }
    Write-Line 'Backend API' (Test-Port 8000) 'port 8000'
}

# --- Frontend ---
if (Test-Port 5173) {
    Write-Line 'Frontend' $true 'already running'
} else {
    $frontendDir = Join-Path $Root 'frontend'
    if (-not (Test-Path (Join-Path $frontendDir 'node_modules'))) {
        Write-Line 'Frontend' $false 'node_modules missing - run: cd frontend; npm install'
    } else {
        Start-Process -FilePath 'powershell' -WindowStyle Minimized -ArgumentList @(
            '-NoExit', '-Command', "Set-Location '$frontendDir'; npm run dev"
        )
        for ($i = 0; $i -lt 30 -and -not (Test-Port 5173); $i++) { Start-Sleep -Seconds 1 }
        Write-Line 'Frontend' (Test-Port 5173) 'port 5173'
    }
}

# --- Report the real health, not just "ports are open" ---
Write-Host ''
if (Test-Port 8000) {
    try {
        $h = Invoke-RestMethod 'http://127.0.0.1:8000/api/health' -TimeoutSec 8
        if ($h.status -eq 'healthy') {
            Write-Host '  Everything is up and healthy.' -ForegroundColor Green
        } else {
            Write-Host "  Running, but degraded:" -ForegroundColor Yellow
            if (-not $h.database)     { Write-Host '    - database unreachable' -ForegroundColor Yellow }
            if (-not $h.llm.reachable){ Write-Host '    - Ollama unreachable' -ForegroundColor Yellow }
            if ($h.llm.detail)        { Write-Host "    - $($h.llm.detail)" -ForegroundColor Yellow }
        }
    } catch {
        Write-Host '  Backend is up but /api/health did not answer yet.' -ForegroundColor Yellow
    }
}

Write-Host ''
Write-Host '  Open:  ' -NoNewline
Write-Host 'http://localhost:5173' -ForegroundColor Cyan
Write-Host ''
Write-Host '  Stop with:    .\start.ps1 -Stop' -ForegroundColor DarkGray
Write-Host '  Check with:   .\start.ps1 -Status' -ForegroundColor DarkGray
Write-Host ''
