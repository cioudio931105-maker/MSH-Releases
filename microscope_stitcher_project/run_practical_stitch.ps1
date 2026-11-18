param(
    [Parameter(Mandatory=$true)]
    [string]$InputPath,

    [string]$OutputPath = "",

    [string]$CoordsPath = "",

    [double]$Overlap = 0.35,

    [ValidateSet("auto", "on", "off")]
    [string]$UseCuda = "auto",

    [ValidateSet("tif", "png", "jpg")]
    [string]$ExportFormat = "tif",

    [ValidateSet("microscope-v1", "normal")]
    [string]$AxisProfile = "microscope-v1",

    [switch]$DisableLearnedTemplate
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not (Test-Path -LiteralPath $InputPath)) {
    throw "InputPath not found: $InputPath"
}

if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $name = Split-Path -Leaf (Resolve-Path -LiteralPath $InputPath)
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutputPath = Join-Path (Join-Path $ScriptDir "..\output") "practical_${name}_${stamp}"
}

$argsList = @(
    (Join-Path $ScriptDir "run_practical_stitch.py"),
    "--input", (Resolve-Path -LiteralPath $InputPath).Path,
    "--output", $OutputPath,
    "--overlap", ([string]::Format("{0:0.####}", $Overlap)),
    "--use-cuda", $UseCuda,
    "--export-format", $ExportFormat,
    "--axis-profile", $AxisProfile
)

if (-not [string]::IsNullOrWhiteSpace($CoordsPath)) {
    if (-not (Test-Path -LiteralPath $CoordsPath)) {
        throw "CoordsPath not found: $CoordsPath"
    }
    $argsList += @("--coords", (Resolve-Path -LiteralPath $CoordsPath).Path)
}

if ($DisableLearnedTemplate) {
    $argsList += "--no-learned-template"
}

Push-Location $ScriptDir
try {
    python @argsList
    if ($LASTEXITCODE -ne 0) {
        throw "run_practical_stitch.py failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
