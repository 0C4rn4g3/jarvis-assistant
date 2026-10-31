# Sets up Jarvis on Windows 10/11: the Python environment and a Start Menu shortcut. Safe to run again.
# Run it from PowerShell in this folder:  powershell -ExecutionPolicy Bypass -File .\install.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv (the Python package manager Jarvis uses)..."
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
if (-not (Test-Path .venv)) { uv venv --python 3.13 .venv }
uv pip install -q --python .venv\Scripts\python.exe -r requirements.txt
uv pip install -q --python .venv\Scripts\python.exe --no-deps openwakeword  # (its tflite dependency has no current wheels)

$config = Join-Path $env:APPDATA "Jarvis"
New-Item -ItemType Directory -Force $config | Out-Null

# Start Menu and Desktop shortcuts; pythonw runs it without a console window
$wsh = New-Object -ComObject WScript.Shell
foreach ($loc in @([Environment]::GetFolderPath("Programs"), [Environment]::GetFolderPath("Desktop"))) {
    $shortcut = $wsh.CreateShortcut((Join-Path $loc "Jarvis.lnk"))
    $shortcut.TargetPath = (Resolve-Path .venv\Scripts\pythonw.exe).Path
    $shortcut.Arguments = "`"$PSScriptRoot\jarvis.py`""
    $shortcut.WorkingDirectory = $PSScriptRoot
    $shortcut.IconLocation = "$PSScriptRoot\icon.ico"
    $shortcut.Description = 'Voice assistant (say "Hey Jarvis")'
    $shortcut.Save()
}

if (-not (Test-Path (Join-Path $config "env"))) {
    # Copy the template so the user has a ready-to-fill file in the right place.
    Copy-Item (Join-Path $PSScriptRoot "env.example") (Join-Path $config "env")
    Write-Host "Next: open $config\env and fill in your Google AI Studio key (GEMINI_API_KEY=...)."
    Write-Host "      Get a free key at https://aistudio.google.com/apikey"
}
Write-Host "Installed. Start Jarvis from the Start Menu (Jarvis)."
Write-Host "Tip:  For CLI commands (--task, --say, --mcp) use .\jarvis-cli.ps1 instead of the shortcut."
