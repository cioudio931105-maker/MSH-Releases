[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][int]$ParentProcessId,
    [Parameter(Mandatory=$true)][string]$InstallerPath,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-fA-F]{64}$')][string]$Sha256
)
$ErrorActionPreference = 'Stop'
try {
    Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Utility\Microsoft.PowerShell.Utility.psd1') -ErrorAction Stop
    # Wait for the existing application to exit normally. Never kill it or its workers.
    $parentProcess = Get-Process -Id $ParentProcessId -ErrorAction SilentlyContinue
    if ($null -ne $parentProcess -and -not $parentProcess.WaitForExit(120000)) {
        throw 'MSH did not exit normally within two minutes; installation cancelled.'
    }
    if (-not (Test-Path -LiteralPath $InstallerPath -PathType Leaf)) { throw 'Installer is missing.' }
    if ((Get-FileHash -LiteralPath $InstallerPath -Algorithm SHA256).Hash -ine $Sha256) {
        throw 'Installer SHA-256 changed after download; installation cancelled.'
    }
    # The user's update action authorizes installation; Windows/vendor permission prompts remain.
    $setupProcess = Start-Process -FilePath $InstallerPath -ArgumentList '/SILENT /SUPPRESSMSGBOXES /SP- /NORESTART /MSHAUTORESTART=1' -Wait -PassThru
    if ($setupProcess.ExitCode -notin @(0, 3010)) { throw "Installer exited with code $($setupProcess.ExitCode)." }
} catch {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show(
        "MSH update was not completed. The previous installation has not been forcibly removed.`r`n`r`n$($_.Exception.Message)",
        'MSH update') | Out-Null
    exit 1
}
