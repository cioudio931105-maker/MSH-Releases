[CmdletBinding()]
param(
    [string]$Destination = "",
    [switch]$IncludeOutputs,
    [switch]$IncludeStitchedOutput,
    [switch]$IncludeModels,
    [switch]$IncludeEnvs,
    [switch]$DryRun,
    [switch]$Help
)
$ErrorActionPreference = "Stop"
$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
if ($Help) {
    Write-Host 'Usage: .\package_for_transfer.ps1 -Destination D:\MSH_source.zip [-DryRun]'
    Write-Host 'Application sources only; models, research data, outputs and environments are never included.'
    return
}
if ($IncludeOutputs -or $IncludeStitchedOutput -or $IncludeModels -or $IncludeEnvs) {
    throw 'Application handoffs cannot include models, research data, outputs or environments. Preserve those separately.'
}
$python = @(
    (Join-Path $root '.venv312\python.exe'),
    (Join-Path $root '.venv312\Scripts\python.exe')
) | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if (-not $python) { $python = (Get-Command python -ErrorAction Stop).Source }
$previousEncoding = $env:PYTHONIOENCODING
try {
    $env:PYTHONIOENCODING = 'utf-8'
    $listJson = & $python (Join-Path $root 'scripts\audit_application_files.py') --list --json
    if ($LASTEXITCODE -ne 0) { throw 'Cannot determine the application-only file list.' }
    $paths = @($listJson | ConvertFrom-Json)
} finally { $env:PYTHONIOENCODING = $previousEncoding }
if (-not $paths.Count) { throw 'No application files found.' }
if ([string]::IsNullOrWhiteSpace($Destination)) {
    $Destination = Join-Path $root ("MSH_portable_{0}.zip" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))
} elseif (-not [System.IO.Path]::IsPathRooted($Destination)) {
    $Destination = Join-Path $root $Destination
}
$destinationFullPath = [System.IO.Path]::GetFullPath($Destination)
Write-Host "Files to package: $($paths.Count)"
Write-Host "Destination: $destinationFullPath"
if ($DryRun) { $paths; return }
if (Test-Path -LiteralPath $destinationFullPath) { throw "Refusing to overwrite archive: $destinationFullPath" }
$destinationDir = Split-Path -Parent $destinationFullPath
if (-not (Test-Path -LiteralPath $destinationDir)) { New-Item -ItemType Directory -Path $destinationDir | Out-Null }
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::Open($destinationFullPath, [System.IO.Compression.ZipArchiveMode]::Create)
try {
    foreach ($path in $paths) {
        [void][System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $archive, (Join-Path $root $path), $path.Replace('\', '/'),
            [System.IO.Compression.CompressionLevel]::Optimal)
    }
} finally { $archive.Dispose() }
Write-Host "Application-only archive created: $destinationFullPath"
