[CmdletBinding()]
param(
    [ValidateSet("Desktop", "StartMenu", "Both")]
    [string]$Location = "Desktop",
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"

$projectRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$launcher = Join-Path $projectRoot "launch_msh.pyw"
$iconPath = Join-Path $projectRoot "assets\msh-pixel-icon.ico"
$shortcutName = "MSH.lnk"
$legacyShortcutName = "MSH 顯微鏡掃描工具.lnk"
$pythonwCandidates = @(
    (Join-Path $projectRoot ".venv312\pythonw.exe"),
    (Join-Path $projectRoot ".venv312\Scripts\pythonw.exe"),
    (Join-Path $projectRoot ".conda-gpu\pythonw.exe"),
    (Join-Path $projectRoot ".venv\Scripts\pythonw.exe")
)
$pythonw = $pythonwCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1

if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
    throw "Missing GUI launcher: $launcher"
}
if (-not $pythonw) {
    throw "Missing windowed Python runtime for MSH."
}
if (-not (Test-Path -LiteralPath $iconPath -PathType Leaf)) {
    throw "Missing MSH shortcut icon: $iconPath"
}

$destinations = @()
if ($Location -in @("Desktop", "Both")) {
    $destinations += [Environment]::GetFolderPath("Desktop")
}
if ($Location -in @("StartMenu", "Both")) {
    $programs = [Environment]::GetFolderPath("Programs")
    $destinations += (Join-Path $programs "MSH")
}

$shell = New-Object -ComObject WScript.Shell
if ($CheckOnly) {
    [PSCustomObject]@{
        TargetPath = $pythonw
        Arguments = "`"$launcher`""
        WorkingDirectory = $projectRoot
        ConsoleRequired = $false
        DiagnosticEntry = (Join-Path $projectRoot "scripts\diagnostics\run_hardware_gui.bat")
    }
    return
}
foreach ($destination in $destinations) {
    New-Item -ItemType Directory -Path $destination -Force | Out-Null
    $shortcutPath = Join-Path $destination $shortcutName
    $legacyShortcutPath = Join-Path $destination $legacyShortcutName
    if (Test-Path -LiteralPath $legacyShortcutPath -PathType Leaf) {
        Remove-Item -LiteralPath $legacyShortcutPath -Force
    }
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $pythonw
    $shortcut.Arguments = "`"$launcher`""
    $shortcut.WorkingDirectory = $projectRoot
    $shortcut.Description = "MSH"
    $shortcut.IconLocation = "$iconPath,0"
    $shortcut.Save()
    Write-Host "Created shortcut: $shortcutPath"
}

Write-Host "Shortcut installation completed."
Write-Host "For diagnostics, run: $projectRoot\scripts\diagnostics\run_hardware_gui.bat"
