# Portable PostgreSQL control script - no installer, no admin rights, no service.
#
# NOTE: keep this file pure ASCII. Windows PowerShell 5.1 decodes .ps1 files as
# Windows-1252 unless they carry a UTF-8 BOM, so a stray em-dash or curly quote
# turns into mojibake and can break parsing outright.
#
# The Postgres binaries live in tools/pgsql and the data directory lives in
# pgdata/, both inside the project. Nothing is written outside this folder and
# nothing is registered with Windows. Deleting the project folder removes every
# trace of the database.
#
# Usage:
#   .\scripts\pg.ps1 init     # one-time: create the data dir, role and database
#   .\scripts\pg.ps1 start
#   .\scripts\pg.ps1 stop
#   .\scripts\pg.ps1 status
#   .\scripts\pg.ps1 psql     # open a SQL shell

param(
    [Parameter(Position = 0)]
    [ValidateSet('init', 'start', 'stop', 'status', 'psql', 'reset')]
    [string]$Action = 'status'
)

$ErrorActionPreference = 'Stop'

$Root    = Split-Path -Parent $PSScriptRoot
$PgBin   = Join-Path $Root 'tools\pgsql\bin'
$PgData  = Join-Path $Root 'pgdata'
$PgLog   = Join-Path $Root 'pgdata\server.log'
$EnvFile = Join-Path $Root '.env'

function Read-EnvValue([string]$Key, [string]$Default) {
    if (-not (Test-Path $EnvFile)) { return $Default }
    foreach ($line in Get-Content $EnvFile) {
        if ($line -match "^\s*$([regex]::Escape($Key))\s*=\s*(.*)$") {
            return $Matches[1].Trim().Trim('"')
        }
    }
    return $Default
}

$DbPort = Read-EnvValue 'POSTGRES_PORT' '5433'
$DbName = Read-EnvValue 'POSTGRES_DB'   'meetmind'
$DbUser = Read-EnvValue 'POSTGRES_USER' 'meetmind'
$DbPass = Read-EnvValue 'POSTGRES_PASSWORD' ''

if (-not (Test-Path $PgBin)) {
    Write-Host "PostgreSQL binaries not found at $PgBin" -ForegroundColor Red
    Write-Host "Run scripts\setup.ps1 first to download them." -ForegroundColor Yellow
    exit 1
}

function Test-Running {
    & "$PgBin\pg_ctl.exe" -D $PgData status *> $null
    return ($LASTEXITCODE -eq 0)
}

switch ($Action) {

    'init' {
        if (Test-Path (Join-Path $PgData 'PG_VERSION')) {
            Write-Host "Data directory already initialised at $PgData" -ForegroundColor Yellow
            Write-Host "Use '.\scripts\pg.ps1 reset' to wipe and start over." -ForegroundColor Yellow
            exit 0
        }
        if (-not $DbPass) {
            Write-Host "POSTGRES_PASSWORD is empty in .env." -ForegroundColor Red
            Write-Host "Run: python scripts\bootstrap_env.py" -ForegroundColor Yellow
            exit 1
        }

        Write-Host "Initialising database cluster..." -ForegroundColor Cyan
        New-Item -ItemType Directory -Force -Path $PgData | Out-Null

        # The superuser password is passed via a temp file, never on the command
        # line, so it can't be read out of the process list by other users.
        $pwFile = Join-Path $env:TEMP "mm_pg_$([guid]::NewGuid().ToString('N')).tmp"
        try {
            Set-Content -Path $pwFile -Value $DbPass -NoNewline -Encoding ascii
            & "$PgBin\initdb.exe" -D $PgData -U postgres --pwfile=$pwFile -E UTF8 --auth-local=scram-sha-256 --auth-host=scram-sha-256 | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "initdb failed with exit code $LASTEXITCODE" }
        }
        finally {
            Remove-Item $pwFile -Force -ErrorAction SilentlyContinue
        }

        # Bind to loopback only. The database is not reachable from the network,
        # from your phone, or from anyone else on your WiFi - by configuration,
        # not by luck.
        $conf = Join-Path $PgData 'postgresql.conf'
        Add-Content -Path $conf -Value @"

# --- MeetMind local settings -------------------------------------------------
listen_addresses = 'localhost'
port = $DbPort
max_connections = 50
shared_buffers = 256MB
password_encryption = scram-sha-256
logging_collector = off
"@

        # Reject every non-loopback host outright.
        $hba = Join-Path $PgData 'pg_hba.conf'
        Set-Content -Path $hba -Value @"
# MeetMind: loopback-only access, SCRAM password required.
local   all   all                  scram-sha-256
host    all   all   127.0.0.1/32   scram-sha-256
host    all   all   ::1/128        scram-sha-256
host    all   all   0.0.0.0/0      reject
"@

        Write-Host "Starting server on port $DbPort..." -ForegroundColor Cyan
        & "$PgBin\pg_ctl.exe" -D $PgData -l $PgLog -o "-p $DbPort" -w start
        if ($LASTEXITCODE -ne 0) { throw "Server failed to start. See $PgLog" }

        $env:PGPASSWORD = $DbPass
        try {
            Write-Host "Creating role '$DbUser' and database '$DbName'..." -ForegroundColor Cyan

            # The role password goes through a psql variable (:'role_pw'), which
            # quotes it safely - so a generated password containing a quote can't
            # break out into SQL. Note this MUST be run via -f: psql performs no
            # variable interpolation for -c, which silently produces a literal
            # ":role_pw" and a syntax error.
            $sqlFile = Join-Path $env:TEMP "mm_role_$([guid]::NewGuid().ToString('N')).sql"
            try {
                Set-Content -Path $sqlFile -Encoding ascii -Value "CREATE ROLE $DbUser LOGIN PASSWORD :'role_pw';"
                & "$PgBin\psql.exe" -U postgres -h 127.0.0.1 -p $DbPort -d postgres -v ON_ERROR_STOP=1 `
                    -v role_pw="$DbPass" -f $sqlFile | Out-Null
                if ($LASTEXITCODE -ne 0) { throw "Could not create role" }
            }
            finally {
                Remove-Item $sqlFile -Force -ErrorAction SilentlyContinue
            }

            & "$PgBin\createdb.exe" -U postgres -h 127.0.0.1 -p $DbPort -O $DbUser $DbName
            if ($LASTEXITCODE -ne 0) { throw "Could not create database" }

            # The app's role owns its own database and nothing else. It is not a
            # superuser: a SQL injection in the app cannot read other databases,
            # write files, or create extensions.
            & "$PgBin\psql.exe" -U postgres -h 127.0.0.1 -p $DbPort -d $DbName -v ON_ERROR_STOP=1 `
                -c "REVOKE ALL ON SCHEMA public FROM PUBLIC; GRANT ALL ON SCHEMA public TO $DbUser;" | Out-Null
        }
        finally {
            Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
        }

        Write-Host ""
        Write-Host "Database ready:  postgresql://$DbUser@127.0.0.1:$DbPort/$DbName" -ForegroundColor Green
        Write-Host "Bound to localhost only. Not reachable from any other machine." -ForegroundColor DarkGray
    }

    'start' {
        if (Test-Running) { Write-Host "Already running on port $DbPort." -ForegroundColor Yellow; exit 0 }
        & "$PgBin\pg_ctl.exe" -D $PgData -l $PgLog -o "-p $DbPort" -w start
        if ($LASTEXITCODE -eq 0) { Write-Host "PostgreSQL started on port $DbPort." -ForegroundColor Green }
        else { Write-Host "Failed to start. Check $PgLog" -ForegroundColor Red; exit 1 }
    }

    'stop' {
        if (-not (Test-Running)) { Write-Host "Not running." -ForegroundColor Yellow; exit 0 }
        & "$PgBin\pg_ctl.exe" -D $PgData -m fast -w stop
        Write-Host "PostgreSQL stopped." -ForegroundColor Green
    }

    'status' {
        if (Test-Running) {
            Write-Host "PostgreSQL is RUNNING on port $DbPort (db=$DbName, user=$DbUser)" -ForegroundColor Green
        } else {
            Write-Host "PostgreSQL is STOPPED" -ForegroundColor Yellow
        }
    }

    'psql' {
        $env:PGPASSWORD = $DbPass
        try { & "$PgBin\psql.exe" -U $DbUser -h 127.0.0.1 -p $DbPort -d $DbName }
        finally { Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue }
    }

    'reset' {
        Write-Host "This deletes the entire database and every meeting in it." -ForegroundColor Red
        $confirm = Read-Host "Type 'DELETE' to confirm"
        if ($confirm -ne 'DELETE') { Write-Host "Cancelled." -ForegroundColor Yellow; exit 0 }
        if (Test-Running) { & "$PgBin\pg_ctl.exe" -D $PgData -m immediate -w stop | Out-Null }
        Remove-Item -Recurse -Force $PgData -ErrorAction SilentlyContinue
        Write-Host "Wiped. Run '.\scripts\pg.ps1 init' to start fresh." -ForegroundColor Green
    }
}
