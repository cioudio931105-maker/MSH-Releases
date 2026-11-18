[CmdletBinding()]
param(
    [switch]$Diagnostics,
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"

$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$guiScript = Join-Path $projectRoot "msh_app\hardware\stepper_drag_gui.py"
$launcher = Join-Path $projectRoot "launch_msh.pyw"
$logDirectory = Join-Path $projectRoot "logs"
$logPath = Join-Path $logDirectory "hardware_gui_startup.log"

function Show-LauncherMessage {
    param(
        [string]$Message,
        [string]$Title = "MSH",
        [ValidateSet("Information", "Warning", "Error")]
        [string]$Kind = "Information"
    )

    Add-Type -AssemblyName System.Windows.Forms
    $icon = [System.Windows.Forms.MessageBoxIcon]::$Kind
    [void][System.Windows.Forms.MessageBox]::Show(
        $Message,
        $Title,
        [System.Windows.Forms.MessageBoxButtons]::OK,
        $icon
    )
}

function Find-PythonRuntime {
    $candidates = @(
        @{ Name = ".venv312"; Python = (Join-Path $projectRoot ".venv312\python.exe"); Pythonw = (Join-Path $projectRoot ".venv312\pythonw.exe") },
        @{ Name = ".venv312 (venv layout)"; Python = (Join-Path $projectRoot ".venv312\Scripts\python.exe"); Pythonw = (Join-Path $projectRoot ".venv312\Scripts\pythonw.exe") },
        @{ Name = ".conda-gpu"; Python = (Join-Path $projectRoot ".conda-gpu\python.exe"); Pythonw = (Join-Path $projectRoot ".conda-gpu\pythonw.exe") },
        @{ Name = ".venv"; Python = (Join-Path $projectRoot ".venv\Scripts\python.exe"); Pythonw = (Join-Path $projectRoot ".venv\Scripts\pythonw.exe") }
    )

    foreach ($candidate in $candidates) {
        if (-not (Test-Path -LiteralPath $candidate.Python -PathType Leaf)) {
            continue
        }

        & $candidate.Python -c "import sys" 2>$null
        if ($LASTEXITCODE -eq 0) {
            $windowed = if (Test-Path -LiteralPath $candidate.Pythonw -PathType Leaf) {
                $candidate.Pythonw
            } else {
                $candidate.Python
            }
            return [PSCustomObject]@{
                Name = $candidate.Name
                Python = $candidate.Python
                WindowedPython = $windowed
            }
        }
    }

    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($null -ne $pythonCommand) {
        & $pythonCommand.Source -c "import sys" 2>$null
        if ($LASTEXITCODE -eq 0) {
            $pythonwCommand = Get-Command pythonw -ErrorAction SilentlyContinue
            return [PSCustomObject]@{
                Name = "PATH"
                Python = $pythonCommand.Source
                WindowedPython = if ($null -ne $pythonwCommand) { $pythonwCommand.Source } else { $pythonCommand.Source }
            }
        }
    }

    return $null
}

try {
    if (-not (Test-Path -LiteralPath $guiScript -PathType Leaf)) {
        throw "找不到 GUI 主程式：$guiScript"
    }
    if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
        throw "找不到 MSH 啟動器：$launcher"
    }

    $runtime = Find-PythonRuntime
    if ($null -eq $runtime) {
        throw "找不到可用的 Python 環境。請先執行專案安裝流程，或使用診斷模式檢查環境。"
    }

    if ($CheckOnly) {
        Write-Output "Project root: $projectRoot"
        Write-Output "GUI script: $guiScript"
        Write-Output "Python environment: $($runtime.Name)"
        Write-Output "Python: $($runtime.Python)"
        Write-Output "Windowed Python: $($runtime.WindowedPython)"
        exit 0
    }

    if ($Diagnostics) {
        Write-Host "MSH hardware GUI diagnostic mode"
        Write-Host "Project root: $projectRoot"
        Write-Host "Python environment: $($runtime.Name)"
        Write-Host "Python: $($runtime.Python)"
        Push-Location -LiteralPath $projectRoot
        try {
            & $runtime.Python $launcher --diagnostics
            exit $LASTEXITCODE
        } finally {
            Pop-Location
        }
    }

    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
    $startedAt = Get-Date
    @(
        "[$($startedAt.ToString('yyyy-MM-dd HH:mm:ss'))] Starting MSH hardware GUI",
        "Project root: $projectRoot",
        "Python environment: $($runtime.Name)",
        "Python: $($runtime.WindowedPython)"
    ) | Set-Content -LiteralPath $logPath -Encoding UTF8

    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $runtime.WindowedPython
    $startInfo.Arguments = '"' + $launcher.Replace('"', '\"') + '"'
    $startInfo.WorkingDirectory = $projectRoot
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    [void]$process.Start()
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    $process.WaitForExit()
    $stdout = $stdoutTask.Result
    $stderr = $stderrTask.Result

    if (-not [string]::IsNullOrWhiteSpace($stdout)) {
        "`n--- stdout ---`n$stdout" | Add-Content -LiteralPath $logPath -Encoding UTF8
    }
    if (-not [string]::IsNullOrWhiteSpace($stderr)) {
        "`n--- stderr ---`n$stderr" | Add-Content -LiteralPath $logPath -Encoding UTF8
    }
    "[$((Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))] Exit code: $($process.ExitCode)" |
        Add-Content -LiteralPath $logPath -Encoding UTF8

    if ($process.ExitCode -ne 0) {
        Show-LauncherMessage -Kind Error -Message "GUI 無法正常啟動。`n`n請執行 scripts\diagnostics\run_hardware_gui.bat 進入診斷模式。`n日誌：$logPath"
        exit $process.ExitCode
    }
} catch {
    $message = $_.Exception.Message
    if ($CheckOnly) {
        [Console]::Error.WriteLine("MSH hardware GUI CheckOnly failed: $message")
        exit 1
    }
    try {
        New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
        "[$((Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))] Launcher error: $($_ | Out-String)" |
            Add-Content -LiteralPath $logPath -Encoding UTF8
    } catch {
        # The message box below remains the fallback when logging is unavailable.
    }
    Show-LauncherMessage -Kind Error -Message "$message`n`n日誌：$logPath"
    exit 1
}
