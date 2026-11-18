[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ArgsList
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$target = Join-Path $root "stitched_output\stitched_output\stitch_cells.ps1"

if (-not (Test-Path $target -PathType Leaf)) {
    throw "Target script not found: $target"
}

& powershell -ExecutionPolicy Bypass -File $target @ArgsList
exit $LASTEXITCODE
