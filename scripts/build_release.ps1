[CmdletBinding()]
param(
    [string]$PythonPath = "",
    [ValidateSet("cpu", "gpu")]
    [string]$Runtime = "cpu",
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$pythonCandidates = @(
    $PythonPath,
    (Join-Path $projectRoot ".venv312\python.exe"),
    (Join-Path $projectRoot ".venv312\Scripts\python.exe")
) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
$python = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if (-not $python) { throw "找不到發行用 Python。請用 -PythonPath 指定乾淨且已驗證的 Python 3.12 環境。" }

& $python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) { throw "缺少 PyInstaller。請執行：$python -m pip install -r requirements-build.txt" }
$torchRuntime = (& $python -c "import torch; print('gpu' if torch.version.cuda else 'cpu')").Trim()
if ($LASTEXITCODE -ne 0) { throw "無法檢查 PyTorch runtime。請確認發行環境已安裝 requirements-$Runtime.txt。" }
if ($torchRuntime -ne $Runtime) {
    throw "發行環境是 $torchRuntime 版 PyTorch，但指定的建置類型是 $Runtime。請使用正確的獨立環境。"
}
$version = (& $python -c "from msh_version import __version__; print(__version__)").Trim()
if ($version -notmatch '^\d+\.\d+\.\d+([-.][0-9A-Za-z.-]+)?$') { throw "msh_version.py 的版本格式無效：$version" }
$releaseModelRelativePath = (& $python -c "from msh_release_model import RELEASE_MODEL_RELATIVE_PATH; print(RELEASE_MODEL_RELATIVE_PATH)").Trim()
$expectedReleaseModelHash = (& $python -c "from msh_release_model import RELEASE_MODEL_SHA256; print(RELEASE_MODEL_SHA256)").Trim().ToLowerInvariant()
$releaseModel = Join-Path $projectRoot $releaseModelRelativePath
if (-not (Test-Path -LiteralPath $releaseModel -PathType Leaf)) {
    throw "缺少核准的 WBC 發行模型：$releaseModel"
}
$actualReleaseModelHash = (Get-FileHash -LiteralPath $releaseModel -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualReleaseModelHash -ne $expectedReleaseModelHash) {
    throw "WBC 發行模型 SHA-256 不符。預期 $expectedReleaseModelHash，實際 $actualReleaseModelHash"
}
$runtimeLabel = $Runtime.ToUpperInvariant()
$distPath = Join-Path "dist" $Runtime
$workPath = Join-Path "build\pyinstaller" $Runtime

Push-Location -LiteralPath $projectRoot
try {
    & $python -m PyInstaller --noconfirm --clean --distpath $distPath --workpath $workPath MSH.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller 建置失敗。請保留 $workPath 供診斷。" }
    $packagedApp = Join-Path $projectRoot "$distPath\MSH\MSH.exe"
    if ($SkipInstaller) { Write-Host "Packaged application: $packagedApp"; exit 0 }

    $iscc = Get-Command iscc.exe -ErrorAction SilentlyContinue
    $isccPath = if ($null -ne $iscc) { $iscc.Source } else {
        @(
            (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
            (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
        ) | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    }
    if (-not $isccPath) { throw "找不到 Inno Setup 6 (ISCC.exe)。請安裝 Inno Setup 後重新執行。" }
    $installerSource = "..\dist\$Runtime\MSH"
    & $isccPath "/DMyAppVersion=$version" "/DMyBuildDir=$installerSource" "/DMyBuildSuffix=$runtimeLabel" "installer\MSH.iss"
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup 建置失敗。" }

    $installer = Join-Path $projectRoot "dist\release\MSH_Setup_v${version}_$runtimeLabel.exe"
    if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) { throw "找不到預期的安裝檔：$installer" }
    $hash = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content -LiteralPath "$installer.sha256" -Value "$hash *$(Split-Path -Leaf $installer)" -Encoding ascii
    Write-Host "Installer: $installer"
    Write-Host "Checksum: $installer.sha256"
} finally {
    Pop-Location
}
