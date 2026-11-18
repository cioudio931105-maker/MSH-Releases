[CmdletBinding()]
param(
    [string]$EnvPath = ".conda-gpu",
    [switch]$RequireCuda,
    [string]$PylonInstallerPath = "",
    [switch]$SkipVerify,
    [switch]$SkipPylon
)

$ErrorActionPreference = "Stop"

$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$root = [System.IO.Path]::GetFullPath($root)

Write-Host "Cell_Project fresh-machine installer"
Write-Host "Workspace root: $root"
Write-Host "Environment path: $EnvPath"

$setupScript = Join-Path $root "scripts\maintenance\setup_gpu_env.ps1"
if (-not (Test-Path -LiteralPath $setupScript)) {
    throw "Missing setup script: $setupScript"
}

$arguments = @{
    EnvPath = $EnvPath
    InstallMiniconda = $true
    UpdateOnly = $false
}

if ($RequireCuda) {
    $arguments.RequireCuda = $true
}
if ($SkipVerify) {
    $arguments.SkipVerify = $true
}
if ($SkipPylon) {
    $arguments.SkipPylon = $true
}
if (-not [string]::IsNullOrWhiteSpace($PylonInstallerPath)) {
    $arguments.PylonInstallerPath = $PylonInstallerPath
}

& $setupScript @arguments
if (-not $?) {
    throw "Project installation failed."
}

Write-Host ""
Write-Host "Installation finished."
Write-Host "If you update the repository later, run .\update_project.ps1"
