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

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"

if ($Help) {
    Write-Host "Usage:"
    Write-Host "  .\package_for_transfer.ps1 -Destination D:\MSH_delivery.zip -IncludeModels -IncludeStitchedOutput"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -Destination <path>       Output zip path. Defaults to MSH_portable_<timestamp>.zip."
    Write-Host "  -IncludeModels            Include .pt/.pth/.onnx model files."
    Write-Host "  -IncludeStitchedOutput    Include captured images and results under stitched_output. Hardware files are always included."
    Write-Host "  -IncludeOutputs           Include output/debug result folders."
    Write-Host "  -IncludeEnvs              Include local environment folders. Usually not recommended."
    Write-Host "  -DryRun                   Show package summary without creating zip."
    return
}

if ([string]::IsNullOrWhiteSpace($Destination)) {
    $Destination = Join-Path $root "MSH_portable_$timestamp.zip"
} elseif (-not [System.IO.Path]::IsPathRooted($Destination)) {
    $Destination = Join-Path $root $Destination
}

$destinationFullPath = [System.IO.Path]::GetFullPath($Destination)

$excludedDirNames = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
foreach ($name in @("__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".idea", ".vscode", ".git")) {
    [void]$excludedDirNames.Add($name)
}

$excludedDirPatterns = @(".conda*", ".venv*")

if (-not $IncludeEnvs) {
    foreach ($name in @(".venv", ".venv312", ".conda-gpu", ".conda", "env", "venv")) {
        [void]$excludedDirNames.Add($name)
    }
}

foreach ($name in @("staging")) {
    [void]$excludedDirNames.Add($name)
}

$excludedRelativeDirs = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
$portableHardwareRelativeDir = "stitched_output\stitched_output\stitched_output\hardware"
if (-not $IncludeOutputs) {
    foreach ($path in @("output", "cell_stitching_project\output", "cell_stitching_project\debug")) {
        [void]$excludedRelativeDirs.Add($path)
    }
}
$excludedFilePatterns = @("*.pyc", "*.pyo", "*.tmp", "*.temp", "*.log", "*.zip", ".cell_project_install.json")
if (-not $IncludeModels) {
    $excludedFilePatterns += @("*.pt", "*.pth", "*.onnx", "*.ckpt")
}

function Normalize-RelativePath {
    param([string]$Path)

    if ([string]::IsNullOrEmpty($Path)) {
        return ""
    }

    $normalized = $Path.Replace("/", "\")
    if ($normalized.StartsWith(".\")) {
        $normalized = $normalized.Substring(2)
    }

    return $normalized
}

function Should-ExcludeDirectory {
    param([string]$RelativePath, [string]$Name)

    $normalized = Normalize-RelativePath $RelativePath
    if ($excludedDirNames.Contains($Name)) {
        return $true
    }

    foreach ($pattern in $excludedDirPatterns) {
        if ($Name -like $pattern) {
            return $true
        }
    }

    if ($excludedRelativeDirs.Contains($normalized)) {
        return $true
    }

    if ($normalized.StartsWith("stitched_output", [System.StringComparison]::OrdinalIgnoreCase) -and -not $IncludeStitchedOutput) {
        $isHardwareBranch = (
            $portableHardwareRelativeDir.StartsWith("$normalized\", [System.StringComparison]::OrdinalIgnoreCase) -or
            $normalized.Equals($portableHardwareRelativeDir, [System.StringComparison]::OrdinalIgnoreCase) -or
            $normalized.StartsWith("$portableHardwareRelativeDir\", [System.StringComparison]::OrdinalIgnoreCase)
        )
        if (-not $isHardwareBranch) {
            return $true
        }
    }

    return $false
}

function Should-ExcludeFile {
    param([string]$RelativePath, [System.IO.FileInfo]$File)

    $normalized = Normalize-RelativePath $RelativePath
    if ($File.FullName -eq $destinationFullPath) {
        return $true
    }

    foreach ($pattern in $excludedFilePatterns) {
        if ($File.Name -like $pattern) {
            return $true
        }
    }

    if (
        $normalized.StartsWith("stitched_output\", [System.StringComparison]::OrdinalIgnoreCase) -and
        -not $IncludeStitchedOutput -and
        -not $normalized.StartsWith("$portableHardwareRelativeDir\", [System.StringComparison]::OrdinalIgnoreCase)
    ) {
        return $true
    }

    return $false
}

function Get-IncludedFiles {
    param(
        [string]$BasePath,
        [string]$RelativePath = ""
    )

    foreach ($item in Get-ChildItem -LiteralPath $BasePath -Force) {
        $nextRelativePath = if ([string]::IsNullOrEmpty($RelativePath)) {
            $item.Name
        } else {
            Join-Path $RelativePath $item.Name
        }

        if ($item.PSIsContainer) {
            if (Should-ExcludeDirectory -RelativePath $nextRelativePath -Name $item.Name) {
                continue
            }

            Get-IncludedFiles -BasePath $item.FullName -RelativePath $nextRelativePath
            continue
        }

        if (Should-ExcludeFile -RelativePath $nextRelativePath -File $item) {
            continue
        }

        [PSCustomObject]@{
            FullName     = $item.FullName
            RelativePath = Normalize-RelativePath $nextRelativePath
            Length       = $item.Length
        }
    }
}

$files = @(Get-IncludedFiles -BasePath $root)

if ($files.Count -eq 0) {
    throw "No files matched the packaging rules."
}

$totalBytes = ($files | Measure-Object -Property Length -Sum).Sum
$sizeMb = [math]::Round($totalBytes / 1MB, 2)

Write-Host "Root: $root"
Write-Host "Destination: $destinationFullPath"
Write-Host "Files to package: $($files.Count)"
Write-Host "Estimated size before zip compression: $sizeMb MB"

if ($DryRun) {
    $files |
        Sort-Object RelativePath |
        Select-Object -First 200 RelativePath, @{Name = "SizeKB"; Expression = { [math]::Round($_.Length / 1KB, 2) } } |
        Format-Table -AutoSize
    return
}

if (Test-Path -LiteralPath $destinationFullPath) {
    Remove-Item -LiteralPath $destinationFullPath -Force
}

$destinationDir = Split-Path -Parent $destinationFullPath
if (-not (Test-Path -LiteralPath $destinationDir)) {
    New-Item -ItemType Directory -Path $destinationDir | Out-Null
}

$zipFile = [System.IO.File]::Open($destinationFullPath, [System.IO.FileMode]::CreateNew)
try {
    $archive = [System.IO.Compression.ZipArchive]::new($zipFile, [System.IO.Compression.ZipArchiveMode]::Create, $false)
    try {
        foreach ($file in $files) {
            $entryName = $file.RelativePath.Replace("\", "/")
            $entry = $archive.CreateEntry($entryName, [System.IO.Compression.CompressionLevel]::Optimal)
            $entryStream = $entry.Open()
            try {
                $sourceStream = [System.IO.File]::OpenRead($file.FullName)
                try {
                    $sourceStream.CopyTo($entryStream)
                } finally {
                    $sourceStream.Dispose()
                }
            } finally {
                $entryStream.Dispose()
            }
        }
    } finally {
        $archive.Dispose()
    }
} finally {
    $zipFile.Dispose()
}

$zipSizeMb = [math]::Round((Get-Item -LiteralPath $destinationFullPath).Length / 1MB, 2)
Write-Host "Archive created: $destinationFullPath ($zipSizeMb MB)"
