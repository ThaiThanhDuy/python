# One-time setup: creates a Start Menu shortcut for "Mouse Corner Macro"
# so you can just click its icon to run it (no terminal needed).
$ErrorActionPreference = "Stop"

$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$runGui = Join-Path $dir "run_gui.bat"

if (-not (Test-Path $runGui)) {
    Write-Error "Khong tim thay $runGui"
    exit 1
}

$programsDir = Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs"
New-Item -ItemType Directory -Force -Path $programsDir | Out-Null
$shortcutPath = Join-Path $programsDir "Mouse Corner Macro.lnk"

$wshell = New-Object -ComObject WScript.Shell
$shortcut = $wshell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $runGui
$shortcut.WorkingDirectory = $dir
$shortcut.WindowStyle = 7  # minimized, avoid flashing a console window
$shortcut.IconLocation = "shell32.dll,23"
$shortcut.Description = "Detect screen size and move the mouse to its 4 corners"
$shortcut.Save()

Write-Host "Da cai dat. Tim 'Mouse Corner Macro' trong Start Menu."
