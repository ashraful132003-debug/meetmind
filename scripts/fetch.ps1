# Resumable downloader with retries.
#
# Built because a slow, flaky connection makes a plain download fail partway and
# throw away everything already fetched. This resumes from wherever it stopped
# (curl -C -), retries indefinitely until complete, and verifies the final size
# so a truncated file is never treated as a good one.
#
# Usage: .\scripts\fetch.ps1 -Url <url> -OutFile <path> [-ExpectedMB 323] [-MaxAttempts 100]

param(
    [Parameter(Mandatory = $true)][string]$Url,
    [Parameter(Mandatory = $true)][string]$OutFile,
    [int]$ExpectedMB = 0,
    [int]$MaxAttempts = 100
)

$ErrorActionPreference = 'Continue'

$dir = Split-Path -Parent $OutFile
if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }

function Get-SizeMB([string]$Path) {
    if (Test-Path $Path) { return [math]::Round((Get-Item $Path).Length / 1MB, 1) }
    return 0
}

# Ask the server how big the file actually is, so completion is verified against
# reality rather than a number hardcoded by me.
$remoteBytes = 0
try {
    $head = curl.exe -sIL --connect-timeout 20 $Url 2>$null
    $lengths = $head | Select-String -Pattern '^\s*content-length:\s*(\d+)' -AllMatches
    if ($lengths) { $remoteBytes = [int64]($lengths[-1].Matches.Groups[1].Value) }
} catch { }

if ($remoteBytes -gt 0) {
    Write-Host ("Remote size: {0} MB" -f [math]::Round($remoteBytes / 1MB, 1))
} elseif ($ExpectedMB -gt 0) {
    $remoteBytes = [int64]($ExpectedMB * 1MB)
    Write-Host "Server did not report a size; using expected $ExpectedMB MB"
}

for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
    $before = Get-SizeMB $OutFile

    if ($remoteBytes -gt 0 -and (Test-Path $OutFile)) {
        if ((Get-Item $OutFile).Length -ge $remoteBytes) {
            Write-Host "COMPLETE: $OutFile ($before MB)" -ForegroundColor Green
            exit 0
        }
    }

    Write-Host ("[attempt {0}] resuming from {1} MB..." -f $attempt, $before)

    # -C -  resume from wherever the local file ends
    # -sS   quiet, but still print real errors
    # --speed-time/--speed-limit  abort a stalled connection rather than hanging
    curl.exe -L -C - -sS `
        --connect-timeout 30 `
        --speed-limit 1000 --speed-time 60 `
        --retry 5 --retry-delay 5 --retry-all-errors `
        -o $OutFile $Url
    $code = $LASTEXITCODE

    $after = Get-SizeMB $OutFile

    if ($code -eq 0) {
        if ($remoteBytes -le 0 -or (Get-Item $OutFile).Length -ge $remoteBytes) {
            Write-Host "COMPLETE: $OutFile ($after MB)" -ForegroundColor Green
            exit 0
        }
        Write-Host "curl exited 0 but file is short ($after MB) - continuing"
    }
    else {
        Write-Host ("  curl exit {0}; progressed {1} -> {2} MB" -f $code, $before, $after) -ForegroundColor DarkYellow
    }

    # Range-not-supported: the server can't resume, so a partial file is useless.
    if ($code -eq 33) {
        Write-Host "Server does not support resume. Restarting from zero." -ForegroundColor Yellow
        Remove-Item $OutFile -Force -ErrorAction SilentlyContinue
    }

    Start-Sleep -Seconds ([math]::Min(30, 3 * $attempt))
}

$final = Get-SizeMB $OutFile
Write-Host ("FAILED after {0} attempts. Got {1} MB." -f $MaxAttempts, $final) -ForegroundColor Red
exit 1
