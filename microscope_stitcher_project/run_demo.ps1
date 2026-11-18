$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

$DemoInput = "D:\microscope_stitcher_demo_input"
$DemoOutput = "D:\microscope_stitcher_demo_output"

if (Test-Path -LiteralPath $DemoInput) {
    Remove-Item -LiteralPath $DemoInput -Recurse -Force
}
if (Test-Path -LiteralPath $DemoOutput) {
    Remove-Item -LiteralPath $DemoOutput -Recurse -Force
}

Push-Location $ProjectRoot
try {
    python tools\generate_demo_dataset.py --output $DemoInput --rows 2 --cols 4 --overlap 0.15
    if ($LASTEXITCODE -ne 0) {
        throw "generate_demo_dataset.py failed with exit code $LASTEXITCODE"
    }

    python run_stitch.py --input $DemoInput --output $DemoOutput --overlap 0.15 --work-scale 0.45 --export-format tif --use-cuda auto
    if ($LASTEXITCODE -ne 0) {
        throw "run_stitch.py failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

Write-Host "Demo output: $DemoOutput"
