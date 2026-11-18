param(
    [string]$InputPath = "C:\Cell_Project\Cell_Project\stitched_output\stitched_output\stitched_output\captured\session_20260521_181641_759929",
    [string]$OutputPath = "C:\Cell_Project\Cell_Project\output\formal_stitch_session_20260521_181641_759929",
    [string]$UseCuda = "auto",
    [switch]$SkipVerify
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Push-Location $ScriptDir
try {
    python ".\run_formal_stitch.py" `
        --input $InputPath `
        --output $OutputPath `
        --overlap 0.35 `
        --exclude "8_0.jpg" `
        --lock-placements ".\reference\session_20260521_181641_759929_golden_placements.csv" `
        --min-edge-score 0.10 `
        --cluster-tolerance-full-px 314 `
        --use-cuda $UseCuda
    if ($LASTEXITCODE -ne 0) {
        throw "run_formal_stitch.py failed with exit code $LASTEXITCODE"
    }

    if (-not $SkipVerify) {
        $GoldenPath = Join-Path $ScriptDir "reference\session_20260521_181641_759929_golden_placements.csv"
        $CandidatePath = Join-Path $OutputPath "debug\placements.csv"
        $CompareJson = Join-Path $OutputPath "debug\golden_compare.json"
        $CompareCsv = Join-Path $OutputPath "debug\golden_compare.csv"

        python ".\tools\compare_against_golden.py" `
            --candidate $CandidatePath `
            --golden $GoldenPath `
            --output-json $CompareJson `
            --output-csv $CompareCsv
        if ($LASTEXITCODE -ne 0) {
            throw "compare_against_golden.py failed with exit code $LASTEXITCODE"
        }
    }
}
finally {
    Pop-Location
}
