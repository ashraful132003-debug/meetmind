# Pull Ollama models, surviving a slow and unreliable connection.
#
# The problem this solves: `ollama pull` does not fail loudly when the connection
# drops. It hangs - the process stays alive, the partial blob stops growing, and
# a naive retry loop waits forever on a download that is never going to finish.
#
# So this watches the partial blob directly. If it stops growing for StallSeconds,
# the pull is killed and restarted; Ollama resumes from the partial, so nothing
# already downloaded is lost.
#
# StallSeconds must be generous. After the bytes are all down, Ollama verifies the
# SHA-256 of the whole blob and writes the manifest - and during that phase the
# file size does not change at all. A short stall timeout kills the pull at 100%,
# every time, and it never finishes. 300s comfortably covers digesting a 2GB blob
# on a slow disk; a genuinely dead connection just waits an extra few minutes
# before resuming, which is a much cheaper mistake.
#
# Keep this file pure ASCII (Windows PowerShell 5.1 decodes .ps1 as Windows-1252).
#
# Usage: .\scripts\pull_models.ps1 [-StallSeconds 300] [-MaxAttempts 60]

param(
    [int]$StallSeconds = 300,
    [int]$MaxAttempts = 60
)

$ErrorActionPreference = 'Continue'

$OllamaExe = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
$BlobDir   = Join-Path $env:USERPROFILE '.ollama\models\blobs'

if (-not (Test-Path $OllamaExe)) {
    Write-Host "Ollama is not installed at $OllamaExe" -ForegroundColor Red
    exit 1
}

$Models = @('all-minilm', 'llama3.2:3b')

function Test-ModelPresent([string]$Name) {
    $list = & $OllamaExe list 2>$null
    if (-not $list) { return $false }
    # A bare name like "all-minilm" is listed as "all-minilm:latest", so match
    # on the base name before the tag.
    $base = [regex]::Escape($Name.Split(':')[0])
    foreach ($line in $list) {
        if ($line -match "^\s*$base(:|\s)") { return $true }
    }
    return $false
}

function Get-PartialBytes {
    if (-not (Test-Path $BlobDir)) { return 0 }
    $files = Get-ChildItem $BlobDir -File -Filter '*partial*' -ErrorAction SilentlyContinue
    if (-not $files) { return 0 }
    return ($files | Measure-Object -Property Length -Sum).Sum
}

function Invoke-PullWithStallWatch([string]$Model) {
    # Start the pull detached so we can watch it and kill it if it wedges.
    $proc = Start-Process -FilePath $OllamaExe -ArgumentList 'pull', $Model `
                          -PassThru -WindowStyle Hidden

    $lastBytes  = Get-PartialBytes
    $lastChange = Get-Date

    while (-not $proc.HasExited) {
        Start-Sleep -Seconds 5

        $now = Get-PartialBytes
        if ($now -ne $lastBytes) {
            $lastBytes  = $now
            $lastChange = Get-Date
            Write-Host ("       {0:N0} MB" -f ($now / 1MB)) -ForegroundColor DarkGray
        }
        elseif (((Get-Date) - $lastChange).TotalSeconds -ge $StallSeconds) {
            Write-Host "       stalled - killing and resuming" -ForegroundColor DarkYellow
            try { $proc.Kill() } catch { }
            # Ollama can leave a worker holding the file handle; give it a beat.
            Start-Sleep -Seconds 3
            return $false
        }
    }

    return (Test-ModelPresent $Model)
}

foreach ($model in $Models) {
    if (Test-ModelPresent $model) {
        Write-Host "[have] $model" -ForegroundColor Green
        continue
    }

    $ok = $false
    for ($i = 1; $i -le $MaxAttempts; $i++) {
        Write-Host "[pull] $model (attempt $i/$MaxAttempts)" -ForegroundColor Cyan

        if (Invoke-PullWithStallWatch $model) {
            Write-Host "[done] $model" -ForegroundColor Green
            $ok = $true
            break
        }

        Start-Sleep -Seconds 3
    }

    if (-not $ok) {
        Write-Host "[fail] $model did not complete after $MaxAttempts attempts" -ForegroundColor Red
        exit 1
    }
}

Write-Host ''
& $OllamaExe list
Write-Host ''
Write-Host 'All models ready.' -ForegroundColor Green
