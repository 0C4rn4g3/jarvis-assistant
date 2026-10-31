# jarvis-cli.ps1 — Run Jarvis CLI commands on Windows from source.
#
# The Start Menu shortcut uses pythonw.exe (no console window), so
# --task, --say and --mcp have nowhere to print. This script uses
# python.exe (with a console) instead, so those commands work fine.
#
# Usage (run from the jarvis-assistant folder, or bind to a key):
#   .\jarvis-cli.ps1 --task "what's on my calendar today?"
#   .\jarvis-cli.ps1 --say "the build finished"
#   .\jarvis-cli.ps1 --listen
#   .\jarvis-cli.ps1 --mcp
#
# You can also add this folder to your PATH and call it from anywhere.

$ScriptDir = $PSScriptRoot
$Python    = Join-Path $ScriptDir ".venv\Scripts\python.exe"
$Jarvis    = Join-Path $ScriptDir "jarvis.py"

if (-not (Test-Path $Python)) {
    Write-Error "Virtual environment not found. Run install.ps1 first."
    exit 1
}

# Pass every argument through to jarvis.py unchanged.
& $Python $Jarvis @args
