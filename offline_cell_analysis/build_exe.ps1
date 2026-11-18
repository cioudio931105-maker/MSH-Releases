$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

cmd /c 'python -c "import PyInstaller" >NUL 2>NUL'
if ($LASTEXITCODE -ne 0) {
    python -m pip install pyinstaller
}

python -m PyInstaller `
    --onefile `
    --windowed `
    --name OfflineCellAnalysis `
    --distpath . `
    --workpath build `
    --specpath build `
    offline_analysis_gui.py

Write-Host "Built: $PSScriptRoot\OfflineCellAnalysis.exe"
