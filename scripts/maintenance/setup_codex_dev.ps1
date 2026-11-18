[CmdletBinding()]
param(
    [ValidateSet("cpu", "gpu", "both")]
    [string]$Mode = "cpu",
    [string]$CpuEnvPath = ".venv312",
    [string]$GpuEnvPath = ".conda-gpu"
)

$ErrorActionPreference = "Stop"

function Resolve-PythonBootstrap {
    try {
        $py = Get-Command py -ErrorAction Stop
        return @{
            Command = $py.Source
            Arguments = @("-3.12")
        }
    } catch {
    }

    try {
        $python = Get-Command python -ErrorAction Stop
        return @{
            Command = $python.Source
            Arguments = @()
        }
    } catch {
    }

    throw "Unable to find Python. Install Python 3.12+ or the Python launcher before running setup_codex_dev.ps1."
}

function Invoke-External {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $FilePath $($Arguments -join ' ')"
    }
}

$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$requirementsPath = Join-Path $root "cell_stitching_project\requirements.txt"

if ($Mode -in @("cpu", "both")) {
    $bootstrap = Resolve-PythonBootstrap
    $cpuEnvFullPath = if ([System.IO.Path]::IsPathRooted($CpuEnvPath)) {
        $CpuEnvPath
    } else {
        Join-Path $root $CpuEnvPath
    }

    Write-Host "Creating CPU development environment at $cpuEnvFullPath"
    Invoke-External -FilePath $bootstrap.Command -Arguments (@($bootstrap.Arguments) + @("-m", "venv", $cpuEnvFullPath))

    $cpuPython = Join-Path $cpuEnvFullPath "Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $cpuPython)) {
        throw "CPU environment was created, but python.exe was not found at $cpuPython"
    }

    Write-Host "Installing CPU development dependencies"
    Invoke-External -FilePath $cpuPython -Arguments @("-m", "pip", "install", "--upgrade", "pip")
    Invoke-External -FilePath $cpuPython -Arguments @("-m", "pip", "install", "-r", $requirementsPath)

    Write-Host "CPU environment ready: $cpuEnvFullPath"
}

if ($Mode -in @("gpu", "both")) {
    $gpuSetupScript = Join-Path $root "scripts\maintenance\setup_gpu_env.ps1"
    Write-Host "Creating GPU development environment at $GpuEnvPath"
    Invoke-External -FilePath "powershell.exe" -Arguments @(
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        $gpuSetupScript,
        "-EnvPath",
        $GpuEnvPath
    )
}

Write-Host ""
Write-Host "Next steps:"
Write-Host "1. Open this folder in VSCode or Codex."
Write-Host "2. Use the CPU env at $CpuEnvPath for editing and smoke tests."
Write-Host "3. Use the GPU env at $GpuEnvPath when you need CUDA validation."
