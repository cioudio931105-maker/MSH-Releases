[CmdletBinding(PositionalBinding = $false)]
param(
    [ValidateSet("stitch", "batch_stitch", "classify")]
    [string]$Mode = "stitch",

    [string]$Folder = "",

    [ValidateSet("auto", "panorama", "scans")]
    [string]$StitcherMode = "auto",

    [ValidateSet("sift", "stitcher")]
    [string]$Backend = "sift",

    [ValidateSet("png", "jpg")]
    [string]$OutputFormat = "png",

    [int]$ResizeWidth = 1500,
    [int]$MaxImages = 0,
    [int]$BatchSize = 15,
    [int]$SiftMaxWidth = 0,

    [switch]$Prewarp,
    [switch]$MergeBatches,
    [switch]$RunInfer,

    [string]$Python = "",

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$InputPaths
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ImageScript = Join-Path $ProjectRoot "scripts\Image.py"
$Requirements = Join-Path $ProjectRoot "requirements.txt"

function Test-PythonCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command,

        [string[]]$Arguments = @("--version")
    )

    try {
        & $Command @Arguments *> $null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Resolve-PythonRuntime {
    if ($Python) {
        if (Test-PythonCommand -Command $Python) {
            return @{
                Command = $Python
                PrefixArgs = @()
            }
        }

        throw "The provided Python executable is not usable: $Python"
    }

    $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if ((Test-Path $venvPython -PathType Leaf) -and (Test-PythonCommand -Command $venvPython)) {
        return @{
            Command = $venvPython
            PrefixArgs = @()
        }
    }

    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher -and (Test-PythonCommand -Command $pyLauncher.Source -Arguments @("-3", "--version"))) {
        return @{
            Command = $pyLauncher.Source
            PrefixArgs = @("-3")
        }
    }

    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd -and (Test-PythonCommand -Command $pythonCmd.Source)) {
        return @{
            Command = $pythonCmd.Source
            PrefixArgs = @()
        }
    }

    return $null
}

function Get-ImageFiles {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $exts = @(".jpg", ".jpeg", ".png", ".bmp")
    $imageFiles = @(
        Get-ChildItem -Path $Path -File -ErrorAction Stop |
            Where-Object { $exts -contains $_.Extension.ToLowerInvariant() }
    )

    $coordMap = Join-Path $Path "virtual_coordinates.csv"
    if (-not (Test-Path $coordMap -PathType Leaf)) {
        return @($imageFiles | Sort-Object Name)
    }

    $lookup = @{}
    foreach ($file in $imageFiles) {
        $lookup[$file.Name.ToLowerInvariant()] = $file
    }

    try {
        $rows = Import-Csv -Path $coordMap | Sort-Object { [int]$_.index }
        $ordered = New-Object System.Collections.Generic.List[object]
        foreach ($row in $rows) {
            $name = [string]$row.filename
            if ([string]::IsNullOrWhiteSpace($name)) {
                continue
            }

            $key = $name.ToLowerInvariant()
            if ($lookup.ContainsKey($key)) {
                [void]$ordered.Add($lookup[$key])
                $lookup.Remove($key)
            }
        }

        if ($ordered.Count -gt 0) {
            Write-Host "[INFO] Using coordinate-map order: $coordMap"
            $remaining = @($lookup.Values | Sort-Object Name)
            return @($ordered + $remaining)
        }
    } catch {
        Write-Host "[WARN] Failed to parse coordinate map, falling back to filename order: $coordMap"
    }

    return @($imageFiles | Sort-Object Name)
}

function Test-ImagePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $ext = [System.IO.Path]::GetExtension($Path)
    return @(".jpg", ".jpeg", ".png", ".bmp") -contains $ext.ToLowerInvariant()
}

function Normalize-InputPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $trimmed = $Path.Trim()
    if ($trimmed.StartsWith('"') -and $trimmed.EndsWith('"')) {
        $trimmed = $trimmed.Trim('"')
    }
    return $trimmed
}

function Get-InteractiveInputPaths {
    Write-Host ""
    Write-Host "貼上圖片資料夾路徑，或貼上 1 張/多張圖片路徑後按 Enter。"
    Write-Host "如果有多個路徑，請用分號 ';' 分隔。直接按 Enter 會用預設資料夾。"

    $rawInput = Read-Host "Input path"
    if ([string]::IsNullOrWhiteSpace($rawInput)) {
        return @()
    }

    return @(
        $rawInput.Split(';') |
            ForEach-Object { Normalize-InputPath -Path $_ } |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    )
}

function Resolve-InputFiles {
    $candidateFiles = @()

    if ($Folder) {
        if (-not (Test-Path $Folder -PathType Container)) {
            throw "Input folder does not exist: $Folder"
        }

        return @(Get-ImageFiles -Path (Resolve-Path $Folder).Path)
    }

    $providedPaths = @($InputPaths | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if (-not $providedPaths.Count) {
        $providedPaths = @(Get-InteractiveInputPaths)
    }

    if ($providedPaths.Count) {
        foreach ($rawPath in $providedPaths) {
            $resolvedInput = Normalize-InputPath -Path $rawPath
            if (-not (Test-Path $resolvedInput)) {
                throw "Input path does not exist: $resolvedInput"
            }

            if (Test-Path $resolvedInput -PathType Container) {
                $candidateFiles += @(Get-ImageFiles -Path (Resolve-Path $resolvedInput).Path)
                continue
            }

            $fullPath = (Resolve-Path $resolvedInput).Path
            if (-not (Test-ImagePath -Path $fullPath)) {
                throw "Unsupported image file: $fullPath"
            }

            $candidateFiles += Get-Item -LiteralPath $fullPath
        }

        $uniqueFiles = @(
            $candidateFiles |
                Sort-Object FullName -Unique
        )

        if (-not $uniqueFiles.Count) {
            throw "No supported image files were found in the provided input."
        }

        return $uniqueFiles
    }

    $candidates = @(
        (Join-Path $ProjectRoot "1"),
        (Join-Path $ProjectRoot "data\cell_images"),
        (Join-Path $ProjectRoot "captured_steps"),
        (Join-Path $ProjectRoot "scripts\cell_images")
    )

    foreach ($candidate in $candidates) {
        if ((Test-Path $candidate -PathType Container) -and (Get-ImageFiles -Path $candidate | Select-Object -First 1)) {
            return @(Get-ImageFiles -Path (Resolve-Path $candidate).Path)
        }
    }

    throw "No input images were found. Provide -Folder or paste image paths when prompted."
}

function Prepare-InputFiles {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$SourceFiles
    )

    $files = @($SourceFiles)
    if (-not $files.Count) {
        throw "No image files were provided."
    }

    $excludePatterns = @(
        "stitched_output*",
        "stitched_batch_*",
        "comparison*",
        "*_results*"
    )

    $filtered = @(
        $files | Where-Object {
            $keep = $true
            foreach ($pattern in $excludePatterns) {
                if ($_.Name -like $pattern) {
                    $keep = $false
                    break
                }
            }
            $keep
        }
    )

    if (-not $filtered.Count) {
        throw "No usable source images remained after filtering."
    }

    $stagingRoot = Join-Path $ProjectRoot "output"
    if (-not (Test-Path $stagingRoot -PathType Container)) {
        New-Item -ItemType Directory -Path $stagingRoot | Out-Null
    }

    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $stageFolder = Join-Path $stagingRoot "stitch_inputs_$stamp"
    New-Item -ItemType Directory -Path $stageFolder | Out-Null

    $index = 1
    foreach ($file in $filtered) {
        $safeName = "img_{0:D4}{1}" -f $index, $file.Extension.ToLowerInvariant()
        Copy-Item -Path $file.FullName -Destination (Join-Path $stageFolder $safeName)
        $index += 1
    }

    Write-Host "[INFO] Prepared an ASCII-safe staged input set."
    Write-Host "[INFO] Using staged input folder: $stageFolder"
    Write-Host "[INFO] Source image count: $($filtered.Count)"
    return $stageFolder
}

function Resolve-StitcherMode {
    param(
        [string]$RequestedMode,
        [string]$InputFolder
    )

    if ($RequestedMode -and $RequestedMode -ne "auto") {
        return $RequestedMode
    }

    if (-not $InputFolder) {
        return "panorama"
    }

    $coordMap = Join-Path $InputFolder "virtual_coordinates.csv"
    if (-not (Test-Path $coordMap -PathType Leaf)) {
        return "panorama"
    }

    try {
        $rows = Import-Csv -Path $coordMap
        if (-not $rows -or $rows.Count -lt 2) {
            return "panorama"
        }

        $xValues = @($rows | ForEach-Object { [int]$_.x } | Select-Object -Unique)
        $yValues = @($rows | ForEach-Object { [int]$_.y } | Select-Object -Unique)
        if ($xValues.Count -eq 1 -or $yValues.Count -eq 1) {
            return "scans"
        }
    } catch {
        Write-Host "[WARN] Failed to infer stitcher mode from coordinate map: $coordMap"
    }

    return "panorama"
}

function Save-TimestampedOutput {
    param(
        [Parameter(Mandatory = $true)]
        [string]$OutputRoot,

        [Parameter(Mandatory = $true)]
        [string]$Extension
    )

    $latestOutput = Join-Path $OutputRoot ("stitched_output." + $Extension)
    if (-not (Test-Path $latestOutput -PathType Leaf)) {
        return
    }

    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $archivedOutput = Join-Path $OutputRoot ("stitched_output_{0}.{1}" -f $timestamp, $Extension)
    Copy-Item -Path $latestOutput -Destination $archivedOutput -Force
    Write-Host "[INFO] Archived output: $archivedOutput"
}

$runtime = Resolve-PythonRuntime
if (-not $runtime) {
    Write-Host "[ERROR] No usable Python runtime was found." -ForegroundColor Red

    $pyVenvCfg = Join-Path $ProjectRoot ".venv\pyvenv.cfg"
    if (Test-Path $pyVenvCfg -PathType Leaf) {
        $homeLine = Select-String -Path $pyVenvCfg -Pattern "^home\s*=\s*(.+)$" -ErrorAction SilentlyContinue
        if ($homeLine) {
            Write-Host "[INFO] Current .venv points to: $($homeLine.Matches[0].Groups[1].Value)"
        }
    }

    Write-Host ""
    Write-Host "Install Python 3.10+ and recreate the virtual environment in this folder:"
    Write-Host "  cd `"$ProjectRoot`""
    Write-Host "  python -m venv .venv"
    Write-Host "  .\.venv\Scripts\python.exe -m pip install --upgrade pip"
    Write-Host "  .\.venv\Scripts\python.exe -m pip install -r `"$Requirements`""
    exit 1
}

if (-not (Test-Path $ImageScript -PathType Leaf)) {
    throw "Image.py not found: $ImageScript"
}

$inputFiles = Resolve-InputFiles
$preparedFolder = Prepare-InputFiles -SourceFiles $inputFiles
$resolvedInputFolder = ""
if ($Folder) {
    $resolvedInputFolder = (Resolve-Path $Folder).Path
}
$resolvedStitcherMode = Resolve-StitcherMode -RequestedMode $StitcherMode -InputFolder $resolvedInputFolder

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$pythonArgs = @()
$pythonArgs += $runtime.PrefixArgs
$pythonArgs += $ImageScript
$pythonArgs += "--mode"
$pythonArgs += $Mode
$pythonArgs += "--folder"
$pythonArgs += $preparedFolder
$pythonArgs += "--max_images"
$pythonArgs += "$MaxImages"
$pythonArgs += "--stitch_backend"
$pythonArgs += $Backend
$pythonArgs += "--stitcher_mode"
$pythonArgs += $resolvedStitcherMode
$pythonArgs += "--resize_width"
$pythonArgs += "$ResizeWidth"
$pythonArgs += "--output_format"
$pythonArgs += $OutputFormat

if (-not $Prewarp) {
    $pythonArgs += "--no_prewarp"
}

if ($SiftMaxWidth -gt 0) {
    $pythonArgs += "--sift_max_width"
    $pythonArgs += "$SiftMaxWidth"
}

if ($Mode -eq "batch_stitch") {
    $pythonArgs += "--batch_size"
    $pythonArgs += "$BatchSize"

    if ($MergeBatches) {
        $pythonArgs += "--merge_batches"
    }
}

if (($Mode -ne "classify") -and (-not $RunInfer)) {
    $pythonArgs += "--skip_infer"
}

Write-Host "[INFO] Mode: $Mode"
Write-Host "[INFO] Backend: $Backend"
Write-Host "[INFO] Stitcher mode: $resolvedStitcherMode"
Write-Host "[INFO] Input folder: $preparedFolder"
$outputRoot = Join-Path $ProjectRoot 'output'
Write-Host "[INFO] Output folder: $outputRoot"

& $runtime.Command @pythonArgs
$exitCode = $LASTEXITCODE

if ($exitCode -ne 0) {
    Write-Host "[ERROR] Stitching command failed with exit code $exitCode." -ForegroundColor Red
} elseif ($Mode -ne "classify") {
    Save-TimestampedOutput -OutputRoot $outputRoot -Extension $OutputFormat
}

exit $exitCode
