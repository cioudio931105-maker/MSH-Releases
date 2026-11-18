[CmdletBinding()]
param(
    [string]$EnvPath = "",
    [ValidateSet("auto", "cpu", "cu118", "cu124")]
    [string]$TorchRuntime = "auto",
    [switch]$Pull,
    [switch]$RequireCuda,
    [switch]$SkipVerify
)

$ErrorActionPreference = "Stop"

function Resolve-GitCommand {
    try {
        $command = Get-Command git -ErrorAction Stop
        if ($command.Source) {
            return $command.Source
        }
    } catch {
    }
    return $null
}

$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$root = [System.IO.Path]::GetFullPath($root)
$statePath = Join-Path $root ".cell_project_install.json"

$resolvedEnvPath = $EnvPath
$resolvedTorchRuntime = $TorchRuntime

if (Test-Path -LiteralPath $statePath) {
    try {
        $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
        if ([string]::IsNullOrWhiteSpace($resolvedEnvPath) -and $state.env_path) {
            $resolvedEnvPath = [string]$state.env_path
        }
    } catch {
        Write-Warning "Unable to read installation state file: $statePath"
    }
}

if ([string]::IsNullOrWhiteSpace($resolvedEnvPath)) {
    $resolvedEnvPath = ".conda-gpu"
}

if ($Pull) {
    $gitCommand = Resolve-GitCommand
    if (-not $gitCommand) {
        throw "Git is not available. Remove -Pull or install Git first."
    }
    if (-not (Test-Path -LiteralPath (Join-Path $root ".git"))) {
        throw "This workspace is not a Git clone. Remove -Pull or update the files manually first."
    }

    Write-Host "Updating repository with git pull --ff-only"
    Push-Location $root
    try {
        & $gitCommand pull --ff-only
        if ($LASTEXITCODE -ne 0) {
            throw "git pull failed with exit code $LASTEXITCODE"
        }
    } finally {
        Pop-Location
    }
}

$setupScript = Join-Path $root "scripts\maintenance\setup_gpu_env.ps1"
if (-not (Test-Path -LiteralPath $setupScript)) {
    throw "Missing setup script: $setupScript"
}

$arguments = @{
    EnvPath = $resolvedEnvPath
    TorchRuntime = $resolvedTorchRuntime
    UpdateOnly = $true
}

if ($RequireCuda) {
    $arguments.RequireCuda = $true
}
if ($SkipVerify) {
    $arguments.SkipVerify = $true
}

& $setupScript @arguments
if (-not $?) {
    throw "Project update failed."
}

Write-Host ""
Write-Host "Update finished."
