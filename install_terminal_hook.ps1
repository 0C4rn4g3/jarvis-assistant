# Installs Jarvis Terminal Error Interceptor into PowerShell Profile
$ProfileDir = Split-Path -Parent $PROFILE
if (-not (Test-Path $ProfileDir)) {
    New-Item -ItemType Directory -Path $ProfileDir -Force | Out-Null
}
if (-not (Test-Path $PROFILE)) {
    New-Item -ItemType File -Path $PROFILE -Force | Out-Null
}

$HookCode = @'

# --- JARVIS TERMINAL ERROR INTERCEPTOR ---
$global:JarvisHookPrompt = $function:prompt
function prompt {
    $lastExit = $LASTEXITCODE
    if ($lastExit -ne 0 -and $lastExit -ne $null) {
        $lastCmd = (Get-History -Count 1 -ErrorAction SilentlyContinue).CommandLine
        $lastErr = ($global:Error[0] | Out-String)
        $currDir = (Get-Location).Path
        if ($lastCmd) {
            Start-Job -ScriptBlock {
                param($c, $e, $o, $w)
                try {
                    $body = @{ command = $c; exit_code = $e; output = $o; cwd = $w } | ConvertTo-Json
                    Invoke-RestMethod -Uri "http://127.0.0.1:4849/api/dev/terminal_error" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 2 -ErrorAction SilentlyContinue | Out-Null
                } catch {}
            } -ArgumentList $lastCmd, $lastExit, $lastErr, $currDir | Out-Null
        }
    }
    if ($global:JarvisHookPrompt) {
        & $global:JarvisHookPrompt
    } else {
        "PS $($executionContext.SessionState.Path.CurrentLocation)$('>' * ($nestedPromptLevel + 1)) "
    }
}
# --- END JARVIS HOOK ---
'@

$ExistingProfile = Get-Content -Path $PROFILE -Raw -ErrorAction SilentlyContinue
if ($ExistingProfile -notmatch "JARVIS TERMINAL ERROR INTERCEPTOR") {
    Add-Content -Path $PROFILE -Value $HookCode
    Write-Host "[Jarvis] Terminal Error Interceptor installed in $PROFILE" -ForegroundColor Green
} else {
    Write-Host "[Jarvis] Terminal Error Interceptor already present in $PROFILE" -ForegroundColor Yellow
}
