param(
    [Parameter(Position = 0)]
    [ValidateSet("help", "install", "run-gui", "list-ports", "run-cli", "clean")]
    [string]$Task = "help",

    [string]$Port = "",
    [int]$Steps = 0,
    [int]$Baud = 115200,
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"

$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Requirements = Join-Path $AppDir "requirements.txt"
$HardwareDir = Join-Path $AppDir "hardware"
$StepperCli = Join-Path $HardwareDir "stepper_cli.py"
$StepperGui = Join-Path $HardwareDir "stepper_drag_gui.py"

function Show-Help {
    Write-Host "Usage:"
    Write-Host "  .\tasks.ps1 help"
    Write-Host "  .\tasks.ps1 install"
    Write-Host "  .\tasks.ps1 run-gui"
    Write-Host "  .\tasks.ps1 list-ports"
    Write-Host "  .\tasks.ps1 run-cli -Port COM3 -Steps 200 [-Baud 115200]"
    Write-Host "  .\tasks.ps1 clean"
}

switch ($Task) {
    "help" {
        Show-Help
    }
    "install" {
        & $Python -m pip install --upgrade pip
        & $Python -m pip install -r $Requirements
    }
    "run-gui" {
        & $Python $StepperGui
    }
    "list-ports" {
        & $Python $StepperCli --list
    }
    "run-cli" {
        if ([string]::IsNullOrWhiteSpace($Port)) {
            throw "Missing -Port. Example: .\tasks.ps1 run-cli -Port COM3 -Steps 200"
        }
        & $Python $StepperCli --port $Port --baud $Baud --steps $Steps
    }
    "clean" {
        Get-ChildItem -Path . -Recurse -Directory -Filter "__pycache__" |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "Removed __pycache__ directories."
    }
}
