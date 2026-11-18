[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ArgsList
)

$ErrorActionPreference = "Stop"

$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$target = Join-Path $root "msh_app\stitch_cells.ps1"

if (-not (Test-Path $target -PathType Leaf)) {
    throw "Target script not found: $target"
}

& powershell -ExecutionPolicy Bypass -File $target @ArgsList
exit $LASTEXITCODE
