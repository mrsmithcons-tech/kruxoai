# Kruxo AI watchdog — runs every 5 min via Task Scheduler.
# Restarts ngrok / the MCP server / the Kruxo app when their process is
# missing, OR when the app is alive but HUNG (its living state file has
# not updated for >3 min — the 26 Nov 13:13 freeze). A hung process passes
# a plain existence check, so state freshness is checked too.
# It NEVER relaunches the app while code is being edited (a source file changed
# in the last 10 minutes) or while a file named watchdog.pause sits in the
# install dir — so it never fights Faisal while he works in the IDE.
# Log: <install-dir>\watchdog.log

$InstallDir = 'C:\Users\Faisal\Downloads\Virtual Ai Assistant'
$LogFile    = Join-Path $InstallDir 'watchdog.log'
$PauseFile  = Join-Path $InstallDir 'watchdog.pause'

function Log($msg) {
    Add-Content -Path $LogFile -Value ("{0} {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg) -ErrorAction SilentlyContinue
}

function Test-EditingRecently {
    $latest = Get-ChildItem (Join-Path $InstallDir 'core'), (Join-Path $InstallDir 'plugins') -Recurse -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $latest) { return $false }
    return ((Get-Date) - $latest.LastWriteTime).TotalMinutes -lt 10
}

function Get-PythonByScript($fragment) {
    Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match [regex]::Escape($fragment) }
}

# --- ngrok (MCP tunnel, port 9877) ---
$ngrok = Get-Process ngrok -ErrorAction SilentlyContinue
if (-not $ngrok) {
    $ngrokExe = (Get-Command ngrok -ErrorAction SilentlyContinue).Source
    if (-not $ngrokExe) {
        $ngrokExe = 'C:\Users\Faisal\AppData\Local\Microsoft\WinGet\Packages\Ngrok.Ngrok_Microsoft.Winget.Source_8wekyb3d8bbwe\ngrok.exe'
    }
    if (Test-Path $ngrokExe) {
        Start-Process -FilePath $ngrokExe -ArgumentList 'http 9877' -WorkingDirectory $InstallDir -WindowStyle Minimized
        Log 'ngrok was down — restarted (http 9877)'
    } else {
        Log 'ngrok was down — ngrok.exe not found, could not restart'
    }
}

# --- MCP server (core/jarvis_mcp_http.py) ---
if (-not (Get-PythonByScript 'jarvis_mcp_http.py')) {
    Start-Process -FilePath python -ArgumentList 'core/jarvis_mcp_http.py' -WorkingDirectory $InstallDir -WindowStyle Minimized
    Log 'MCP server was down — restarted'
}

# --- Kruxo app (python main.py) ---
# Launch via run_hidden.bat with a HIDDEN window (no console for anyone to
# close by accident — the 26 Nov deaths all followed a visible console
# window; the log showed a Ctrl+C).
# Two failure modes: process missing, OR process alive but HUNG (living
# state file not updated for >3 min — the 26 Nov 13:13 freeze, when the
# app was alive but the tick loop had stopped). The 3-minute process-age
# guard keeps the watchdog from killing a fresh boot (boot takes 60-90 s
# before the first tick lands). Duplicate instances are all killed so only
# one survives.
$app = Get-PythonByScript 'main.py' | Sort-Object CreationDate
$hung = $false
$stateAgeSec = 0
if ($app) {
    $stateFile = Join-Path $InstallDir 'memory\living_state.json'
    if (Test-Path $stateFile) {
        $stateAgeSec = [int]((Get-Date) - (Get-Item $stateFile).LastWriteTime).TotalSeconds
        $procAgeMin = ((Get-Date) - $app[0].CreationDate).TotalMinutes
        if ($stateAgeSec -gt 180 -and $procAgeMin -gt 3) { $hung = $true }
    }
}
if (-not $app -or $hung) {
    if (Test-Path $PauseFile) {
        Log 'app is down/hung — paused by watchdog.pause, not restarting'
    } elseif (Test-EditingRecently) {
        Log 'app is down/hung — source files changed in the last 10 min (editing?), not restarting'
    } else {
        if ($hung) {
            foreach ($p in $app) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
            Log ("app hung (state stale {0}s) — killed {1} process(es)" -f $stateAgeSec, $app.Count)
        }
        Start-Process -FilePath (Join-Path $InstallDir 'run_hidden.bat') -WindowStyle Hidden
        Log 'app was down/hung — restarted via run_hidden.bat (hidden)'
    }
}
