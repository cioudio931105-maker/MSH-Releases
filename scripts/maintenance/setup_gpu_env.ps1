[CmdletBinding()]
param(
    [string]$EnvPath = ".conda-gpu",
    [switch]$SkipVerify,
    [switch]$RequireCuda,
    [ValidateSet("auto", "cpu", "cu118", "cu124")]
    [string]$TorchRuntime = "auto",
    [switch]$InstallMiniconda,
    [string]$MinicondaRoot = "",
    [switch]$UpdateOnly,
    [string]$PylonInstallerPath = "",
    [switch]$SkipPylon
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message"
}

function Invoke-ExternalOrThrow {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$StepName
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$StepName failed with exit code $LASTEXITCODE"
    }
}

function Test-CondaEnvironmentExists {
    param([string]$Path)

    return (Test-Path -LiteralPath (Join-Path $Path "conda-meta\history"))
}

function Resolve-CondaCommand {
    $candidates = [System.Collections.Generic.List[string]]::new()

    if ($env:CONDA_EXE) {
        $candidates.Add($env:CONDA_EXE)
    }

    try {
        $command = Get-Command conda -ErrorAction Stop
        if ($command.Source) {
            $candidates.Add($command.Source)
        }
    } catch {
    }

    try {
        $whereResults = @(where.exe conda 2>$null)
        foreach ($result in $whereResults) {
            if (-not [string]::IsNullOrWhiteSpace($result)) {
                $candidates.Add($result.Trim())
            }
        }
    } catch {
    }

    $userProfile = [Environment]::GetFolderPath("UserProfile")
    foreach ($path in @(
        (Join-Path $userProfile "miniconda3\condabin\conda.bat"),
        (Join-Path $userProfile "miniconda3\Scripts\conda.exe"),
        (Join-Path $userProfile "anaconda3\condabin\conda.bat"),
        (Join-Path $userProfile "anaconda3\Scripts\conda.exe"),
        (Join-Path $userProfile "mambaforge\condabin\conda.bat"),
        (Join-Path $userProfile "mambaforge\Scripts\conda.exe"),
        "C:\ProgramData\Miniconda3\condabin\conda.bat",
        "C:\ProgramData\Miniconda3\Scripts\conda.exe",
        "C:\ProgramData\Anaconda3\condabin\conda.bat",
        "C:\ProgramData\Anaconda3\Scripts\conda.exe"
    )) {
        $candidates.Add($path)
    }

    $seen = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($candidate in $candidates) {
        if ([string]::IsNullOrWhiteSpace($candidate)) {
            continue
        }

        $fullPath = [System.IO.Path]::GetFullPath($candidate)
        if ((-not $seen.Add($fullPath)) -or (-not (Test-Path -LiteralPath $fullPath))) {
            continue
        }

        return $fullPath
    }

    return $null
}

function Install-Miniconda {
    param([string]$TargetRoot)

    $downloadUrl = "https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe"
    $downloadDir = Join-Path ([System.IO.Path]::GetTempPath()) "cell_project_bootstrap"
    $installerPath = Join-Path $downloadDir "Miniconda3-latest-Windows-x86_64.exe"

    if (-not (Test-Path -LiteralPath $downloadDir)) {
        New-Item -ItemType Directory -Force -Path $downloadDir | Out-Null
    }

    Write-Step "Conda not found. Downloading Miniconda to $installerPath"
    Invoke-WebRequest -Uri $downloadUrl -OutFile $installerPath

    if (-not (Test-Path -LiteralPath $TargetRoot)) {
        New-Item -ItemType Directory -Force -Path $TargetRoot | Out-Null
    }

    Write-Step "Installing Miniconda to $TargetRoot"
    $arguments = @(
        "/InstallationType=JustMe",
        "/RegisterPython=0",
        "/AddToPath=0",
        "/S",
        "/D=$TargetRoot"
    )

    $process = Start-Process -FilePath $installerPath -ArgumentList $arguments -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        throw "Miniconda installation failed with exit code $($process.ExitCode)"
    }
}

function Resolve-OrInstallCondaCommand {
    param(
        [string]$RequestedRoot,
        [switch]$AllowInstall
    )

    $existing = Resolve-CondaCommand
    if ($existing) {
        return $existing
    }

    if (-not $AllowInstall) {
        throw "Unable to find Conda. Install Conda first or rerun with -InstallMiniconda."
    }

    $targetRoot = $RequestedRoot
    if ([string]::IsNullOrWhiteSpace($targetRoot)) {
        $targetRoot = Join-Path ([Environment]::GetFolderPath("UserProfile")) "miniconda3"
    }
    $targetRoot = [System.IO.Path]::GetFullPath($targetRoot)

    Install-Miniconda -TargetRoot $targetRoot

    $resolved = Resolve-CondaCommand
    if (-not $resolved) {
        throw "Miniconda was installed, but Conda still could not be resolved."
    }
    return $resolved
}

function Get-NvidiaGpuNames {
    $names = [System.Collections.Generic.List[string]]::new()

    try {
        $nvidiaSmi = Get-Command nvidia-smi -ErrorAction Stop
        $query = & $nvidiaSmi.Source "--query-gpu=name" "--format=csv,noheader" 2>$null
        if ($LASTEXITCODE -eq 0) {
            foreach ($line in $query) {
                if (-not [string]::IsNullOrWhiteSpace($line)) {
                    $names.Add($line.Trim())
                }
            }
        }
    } catch {
    }

    if ($names.Count -eq 0) {
        try {
            $controllers = Get-CimInstance Win32_VideoController -ErrorAction Stop
            foreach ($controller in $controllers) {
                if ($controller.Name -and $controller.Name -match "NVIDIA") {
                    $names.Add($controller.Name.Trim())
                }
            }
        } catch {
        }
    }

    return @($names | Select-Object -Unique)
}

function Get-TorchIndexUrl {
    param([string]$Runtime)

    switch ($Runtime) {
        "cpu" { return "https://download.pytorch.org/whl/cpu" }
        "cu118" { return "https://download.pytorch.org/whl/cu118" }
        "cu124" { return "https://download.pytorch.org/whl/cu124" }
        default { throw "Unsupported torch runtime: $Runtime" }
    }
}

function Get-TorchRuntimeCandidates {
    param(
        [string]$RequestedRuntime,
        [string[]]$GpuNames
    )

    if ($RequestedRuntime -ne "auto") {
        return @($RequestedRuntime)
    }

    if ($GpuNames.Count -gt 0) {
        return @("cu124", "cu118", "cpu")
    }

    return @("cpu")
}

function Invoke-CondaPython {
    param(
        [string]$CondaCommand,
        [string]$EnvironmentPath,
        [string[]]$PythonArguments,
        [string]$StepName
    )

    $allArguments = @("run", "-p", $EnvironmentPath, "python") + $PythonArguments
    Invoke-ExternalOrThrow -FilePath $CondaCommand -Arguments $allArguments -StepName $StepName
}

function Install-TorchRuntime {
    param(
        [string]$CondaCommand,
        [string]$EnvironmentPath,
        [string]$Runtime,
        [switch]$RequireCuda
    )

    $indexUrl = Get-TorchIndexUrl -Runtime $Runtime

    Write-Step "Installing PyTorch runtime: $Runtime"
    Invoke-CondaPython -CondaCommand $CondaCommand -EnvironmentPath $EnvironmentPath -PythonArguments @("-m", "pip", "uninstall", "-y", "torch", "torchvision", "torchaudio") -StepName "PyTorch uninstall cleanup" | Out-Host
    Invoke-CondaPython -CondaCommand $CondaCommand -EnvironmentPath $EnvironmentPath -PythonArguments @("-m", "pip", "install", "--upgrade", "--no-cache-dir", "pip") -StepName "pip upgrade" | Out-Host
    Invoke-CondaPython -CondaCommand $CondaCommand -EnvironmentPath $EnvironmentPath -PythonArguments @("-m", "pip", "install", "--no-cache-dir", "torch", "torchvision", "--index-url", $indexUrl) -StepName "PyTorch $Runtime install" | Out-Host

    $verificationScript = "import json, sys, torch; payload={'torch': torch.__version__, 'cuda_available': bool(torch.cuda.is_available()), 'torch_cuda': torch.version.cuda, 'gpu': torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'n/a'}; print(json.dumps(payload)); requested=sys.argv[1]; require_cuda=(sys.argv[2]=='1'); sys.exit(0 if ((requested=='cpu' and not require_cuda) or payload['cuda_available']) else (2 if require_cuda else 3))"

    try {
        Invoke-CondaPython -CondaCommand $CondaCommand -EnvironmentPath $EnvironmentPath -PythonArguments @("-c", $verificationScript, $Runtime, ($(if ($RequireCuda) { "1" } else { "0" }))) -StepName "PyTorch runtime verification" | Out-Host
        return $true
    } catch {
        if ($Runtime -eq "cpu") {
            throw
        }
        Write-Warning "PyTorch runtime $Runtime did not verify successfully. Trying the next candidate."
        return $false
    }
}

function Write-InstallState {
    param(
        [string]$Root,
        [string]$EnvironmentPath,
        [string]$TorchRuntime,
        [string[]]$GpuNames
    )

    $statePath = Join-Path $Root ".cell_project_install.json"
    $state = [ordered]@{
        env_path = $EnvironmentPath
        torch_runtime = $TorchRuntime
        nvidia_gpu_detected = ($GpuNames.Count -gt 0)
        nvidia_gpu_names = $GpuNames
        updated_at = (Get-Date).ToString("s")
    }
    $stateJson = $state | ConvertTo-Json -Depth 4
    [System.IO.File]::WriteAllText($statePath, $stateJson, [System.Text.UTF8Encoding]::new($false))
}

$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$root = [System.IO.Path]::GetFullPath($root)
$fullEnvPath = if ([System.IO.Path]::IsPathRooted($EnvPath)) {
    [System.IO.Path]::GetFullPath($EnvPath)
} else {
    Join-Path $root $EnvPath
}
$tempRoot = Join-Path $fullEnvPath "_pip_tmp"
$requirementsPath = Join-Path $root "cell_stitching_project\requirements.txt"
$requirementsGpuPath = Join-Path $root "cell_stitching_project\requirements-gpu.txt"
$ultralyticsDeps = @(
    "pyyaml",
    "requests",
    "psutil",
    "polars",
    "ultralytics-thop"
)

$condaCommand = Resolve-OrInstallCondaCommand -RequestedRoot $MinicondaRoot -AllowInstall:$InstallMiniconda
$gpuNames = @(Get-NvidiaGpuNames)
$runtimeCandidates = @(Get-TorchRuntimeCandidates -RequestedRuntime $TorchRuntime -GpuNames $gpuNames)

Write-Host "Workspace root: $root"
Write-Host "Using Conda command: $condaCommand"
Write-Host "Environment path: $fullEnvPath"
if ($gpuNames.Count -gt 0) {
    Write-Host "Detected NVIDIA GPU(s): $($gpuNames -join '; ')"
} else {
    Write-Host "Detected NVIDIA GPU(s): none"
}
Write-Host "Torch runtime candidates: $($runtimeCandidates -join ', ')"

if (-not (Test-CondaEnvironmentExists -Path $fullEnvPath)) {
    Write-Step "Creating Conda environment"
    Invoke-ExternalOrThrow -FilePath $condaCommand -Arguments @("create", "-p", $fullEnvPath, "python=3.12", "-y") -StepName "Conda environment creation"
} elseif (-not $UpdateOnly) {
    Write-Step "Conda environment already exists. Reusing it."
}

if (-not (Test-Path -LiteralPath $tempRoot)) {
    New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
}
$env:TMP = $tempRoot
$env:TEMP = $tempRoot
$env:PIP_NO_CACHE_DIR = "1"

$selectedRuntime = $null
foreach ($candidate in $runtimeCandidates) {
    $verified = Install-TorchRuntime -CondaCommand $condaCommand -EnvironmentPath $fullEnvPath -Runtime $candidate -RequireCuda:$RequireCuda
    if ($verified) {
        $selectedRuntime = $candidate
        break
    }
}

if (-not $selectedRuntime) {
    throw "Unable to install a working PyTorch runtime. Tried: $($runtimeCandidates -join ', ')"
}

if (-not $SkipPylon -and [string]::IsNullOrWhiteSpace($PylonInstallerPath)) {
    Write-Warning "Basler full functionality still requires the official Basler Pylon runtime/SDK. If you already have the installer, rerun with -PylonInstallerPath."
}

if (-not $SkipPylon -and -not [string]::IsNullOrWhiteSpace($PylonInstallerPath)) {
    $resolvedPylonPath = if ([System.IO.Path]::IsPathRooted($PylonInstallerPath)) {
        [System.IO.Path]::GetFullPath($PylonInstallerPath)
    } else {
        Join-Path $root $PylonInstallerPath
    }
    if (-not (Test-Path -LiteralPath $resolvedPylonPath)) {
        throw "Basler Pylon installer not found: $resolvedPylonPath"
    }
    Write-Step "Launching Basler Pylon installer"
    Write-Host "Complete the vendor installer, then return to this window."
    $process = Start-Process -FilePath $resolvedPylonPath -PassThru
    $process.WaitForExit()
}

Write-Step "Installing project and GPU dependencies"
$projectInstallArguments = @("-m", "pip", "install", "--upgrade", "--no-cache-dir", "-r", $requirementsGpuPath) + $ultralyticsDeps
Invoke-CondaPython -CondaCommand $condaCommand -EnvironmentPath $fullEnvPath -PythonArguments $projectInstallArguments -StepName "Project dependency install"

Write-Step "Installing Ultralytics without replacing the selected torch runtime"
Invoke-CondaPython -CondaCommand $condaCommand -EnvironmentPath $fullEnvPath -PythonArguments @("-m", "pip", "install", "--upgrade", "--no-cache-dir", "--no-deps", "ultralytics") -StepName "Ultralytics install"

Write-Step "Validating the environment python executable directly"
$directPython = Join-Path $fullEnvPath "python.exe"
Invoke-ExternalOrThrow -FilePath $directPython -Arguments @("-c", "import cv2, torch; print('cv2', cv2.__version__); print('torch', torch.__version__)") -StepName "Direct environment python validation"

Write-Step "Recording installation state"
Write-InstallState -Root $root -EnvironmentPath $fullEnvPath -TorchRuntime $selectedRuntime -GpuNames $gpuNames

if (-not $SkipVerify) {
    Write-Step "Running project environment verification"
    $verifyArgs = @(
        "-m",
        "cell_stitching_project.verify_environment",
        "--workspace-root",
        $root
    )
    if ($RequireCuda) {
        $verifyArgs += "--require-cuda"
    } else {
        $verifyArgs += "--skip-basler-enumeration"
    }
    Invoke-CondaPython -CondaCommand $condaCommand -EnvironmentPath $fullEnvPath -PythonArguments $verifyArgs -StepName "Project environment verification"
}

Write-Step "Environment ready"
Write-Host "Selected torch runtime: $selectedRuntime"
Write-Host "Python path: $(Join-Path $fullEnvPath 'python.exe')"
Write-Host "To refresh dependencies later, run: .\update_project.ps1"
