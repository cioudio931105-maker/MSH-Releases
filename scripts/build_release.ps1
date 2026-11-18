[CmdletBinding()]
param(
    [string]$PythonPath = "",
    [ValidateSet("cpu", "gpu")]
    [string]$Runtime = "cpu",
    [switch]$Candidate,
    [switch]$SkipInstaller,
    [string]$PublicBaseUrl = "",
    [string]$ReleasePageUrl = ""
)

$ErrorActionPreference = "Stop"
if (-not [string]::IsNullOrWhiteSpace($PublicBaseUrl) -and ($Candidate -or $SkipInstaller)) {
    throw "PublicBaseUrl requires a release installer; Candidate and SkipInstaller cannot be finalized."
}
if (-not [string]::IsNullOrWhiteSpace($ReleasePageUrl) -and [string]::IsNullOrWhiteSpace($PublicBaseUrl)) {
    throw "ReleasePageUrl requires PublicBaseUrl."
}
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
$releaseNotes = Join-Path $projectRoot "docs\release\RELEASE_NOTES_v$version.md"
if (-not (Test-Path -LiteralPath $releaseNotes -PathType Leaf)) {
    throw "缺少版本專屬 release notes：$releaseNotes"
}
$runtimeLabel = $Runtime.ToUpperInvariant()
$buildMode = if ($Candidate) { "candidate" } else { "release" }
if ($Candidate) { $runtimeLabel = "${runtimeLabel}_CANDIDATE" }
$installer = Join-Path $projectRoot "dist\release\v$version\MSH_Setup_v${version}_$runtimeLabel.exe"
if (-not $SkipInstaller -and (Test-Path -LiteralPath $installer)) {
    throw "拒絕覆寫既有發行產物：$installer。請升版，或使用新的候選版本。"
}
$distPath = Join-Path "dist" $Runtime
$workPath = Join-Path "build\pyinstaller" $Runtime
$publishedApp = Join-Path $projectRoot "$distPath\MSH"
$stagingRoot = Join-Path $projectRoot ("build\release-staging\{0}-{1}" -f $Runtime, [guid]::NewGuid().ToString("N"))
$stagingDistPath = Join-Path $stagingRoot "dist"
$stagingWorkPath = Join-Path $stagingRoot "work"
$stagingApp = Join-Path $stagingDistPath "MSH"
$buildManifestName = "MSH-build-manifest.json"

function Get-Sha256([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "找不到必需檔案，無法建立可追溯的發行包：$Path"
    }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Remove-GeneratedDirectory([string]$Path, [string]$AllowedParent) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $resolvedPath = [System.IO.Path]::GetFullPath($Path)
    $resolvedParent = [System.IO.Path]::GetFullPath($AllowedParent)
    if (-not $resolvedPath.StartsWith($resolvedParent + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "拒絕刪除預期輸出目錄以外的路徑：$resolvedPath"
    }
    Remove-Item -LiteralPath $resolvedPath -Recurse -Force
}

Push-Location -LiteralPath $projectRoot
try {
    # Build into a new directory.  Never let Inno Setup consume a previous
    # dist\<runtime>\MSH tree after a failed or skipped PyInstaller build.
    New-Item -ItemType Directory -Force -Path $stagingRoot | Out-Null
    & $python -m PyInstaller --noconfirm --clean --distpath $stagingDistPath --workpath $stagingWorkPath MSH.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller 建置失敗。請保留 $workPath 供診斷。" }
    $packagedApp = Join-Path $stagingApp "MSH.exe"
    if (-not (Test-Path -LiteralPath $packagedApp -PathType Leaf)) {
        throw "PyInstaller 沒有產生預期的 MSH.exe：$packagedApp"
    }
    $forbiddenWeights = @(Get-ChildItem -LiteralPath $stagingApp -File -Recurse | Where-Object {
        $_.Extension.ToLowerInvariant() -in @('.pt', '.pth', '.ckpt', '.onnx', '.engine', '.safetensors', '.tflite', '.h5', '.keras', '.pb', '.pfs', '.weights', '.omc', '.caffemodel')
    })
    if ($forbiddenWeights.Count -gt 0) {
        throw "發行包含有禁止散布的模型或設備設定，拒絕建立安裝檔：$($forbiddenWeights.Name -join ', ')"
    }

    $gitCommit = (& git -C $projectRoot rev-parse HEAD).Trim().ToLowerInvariant()
    if ($LASTEXITCODE -ne 0 -or $gitCommit -notmatch '^[0-9a-f]{40}$') {
        throw "無法取得目前 Git commit；拒絕建立無法追溯的發行包。"
    }
    $gitDirtyPaths = @(& git -C $projectRoot status --porcelain)
    if ($LASTEXITCODE -ne 0) { throw "無法讀取 Git 工作樹狀態；拒絕建立無法追溯的發行包。" }
    $releaseTag = "v$version"
    if (-not $Candidate) {
        if ($gitDirtyPaths.Count -gt 0) { throw "正式發行禁止使用含未提交變更的工作樹。請先 commit，或明確使用 -Candidate。" }
        $tagCommitOutput = & git -C $projectRoot rev-list -n 1 $releaseTag 2>$null
        $tagCommit = if ($null -eq $tagCommitOutput) { "" } else { ([string]$tagCommitOutput).Trim().ToLowerInvariant() }
        if ($tagCommit -ne $gitCommit) { throw "正式發行要求 HEAD 有對應 tag $releaseTag。請先建立並審核 tag，或使用 -Candidate。" }
    }
    $sourceFiles = [ordered]@{
        "launch_msh.pyw" = (Join-Path $projectRoot "launch_msh.pyw")
        "msh_version.py" = (Join-Path $projectRoot "msh_version.py")
        "MSH.spec" = (Join-Path $projectRoot "MSH.spec")
        "msh_model_policy.py" = (Join-Path $projectRoot "msh_model_policy.py")
        "msh_motion_policy.py" = (Join-Path $projectRoot "msh_motion_policy.py")
        "msh_runtime.py" = (Join-Path $projectRoot "msh_runtime.py")
        "msh_workers.py" = (Join-Path $projectRoot "msh_workers.py")
        "msh_distribution.py" = (Join-Path $projectRoot "msh_distribution.py")
        "LICENSE" = (Join-Path $projectRoot "LICENSE")
        "THIRD_PARTY_NOTICES.md" = (Join-Path $projectRoot "THIRD_PARTY_NOTICES.md")
        "hardware/arduino_stepper.py" = (Join-Path $projectRoot "msh_app\hardware\arduino_stepper.py")
        "hardware/stepper_drag_gui.py" = (Join-Path $projectRoot "msh_app\hardware\stepper_drag_gui.py")
    }
    $sourceHashes = [ordered]@{}
    foreach ($entry in $sourceFiles.GetEnumerator()) { $sourceHashes[$entry.Key] = Get-Sha256 $entry.Value }
    $noticeHashes = [ordered]@{}
    foreach ($notice in (Get-ChildItem -LiteralPath (Join-Path $projectRoot 'licenses') -File -Recurse | Sort-Object FullName)) {
        $relative = $notice.FullName.Substring($projectRoot.Length + 1).Replace('\', '/')
        $noticeHashes[$relative] = Get-Sha256 $notice.FullName
    }
    $buildManifest = [ordered]@{
        schema_version = 1
        application = "MSH"
        version = $version
        build_mode = $buildMode
        runtime = $Runtime
        git_commit = $gitCommit
        git_worktree_dirty = ($gitDirtyPaths.Count -gt 0)
        git_dirty_paths = $gitDirtyPaths
        built_utc = [DateTime]::UtcNow.ToString("o")
        python_version = (& $python --version).Trim()
        pyinstaller_version = (& $python -c "import PyInstaller; print(PyInstaller.__version__)").Trim()
        torch_version = (& $python -c "import torch; print(torch.__version__)").Trim()
        app_exe_sha256 = Get-Sha256 $packagedApp
        source_sha256 = $sourceHashes
        model_distribution = "user-supplied"
        bundled_models = @()
        bundled_research_data = $false
        source_license = 'AGPL-3.0-only'
        license_notice_sha256 = $noticeHashes
    }
    $buildManifestPath = Join-Path $stagingApp $buildManifestName
    $buildManifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $buildManifestPath -Encoding utf8

    # Publish only a successful fresh build for local smoke tests.  This is a
    # generated, ignored directory; it is never an input to the installer.
    Remove-GeneratedDirectory $publishedApp (Join-Path $projectRoot $distPath)
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $publishedApp) | Out-Null
    Copy-Item -LiteralPath $stagingApp -Destination $publishedApp -Recurse
    if ((Get-Sha256 (Join-Path $publishedApp $buildManifestName)) -ne (Get-Sha256 $buildManifestPath)) {
        throw "發行 payload 複製後的建置證據不一致。"
    }
    if ($SkipInstaller) {
        Write-Host "Packaged application: $publishedApp"
        Write-Host "Build manifest: $(Join-Path $publishedApp $buildManifestName)"
        exit 0
    }

    $installer = Join-Path $projectRoot "dist\release\v$version\MSH_Setup_v${version}_$runtimeLabel.exe"
    if (Test-Path -LiteralPath $installer) {
        throw "拒絕覆寫既有發行產物：$installer。請升版，或使用新的候選版本。"
    }
    $iscc = Get-Command iscc.exe -ErrorAction SilentlyContinue
    $isccPath = if ($null -ne $iscc) { $iscc.Source } else {
        @(
            (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
            (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
        ) | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    }
    if (-not $isccPath) { throw "找不到 Inno Setup 6 (ISCC.exe)。請安裝 Inno Setup 後重新執行。" }
    & $isccPath "/DMyAppVersion=$version" "/DMyBuildDir=$stagingApp" "/DMyBuildSuffix=$runtimeLabel" "installer\MSH.iss"
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup 建置失敗。" }

    if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) { throw "找不到預期的安裝檔：$installer" }
    $hash = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content -LiteralPath "$installer.sha256" -Value "$hash *$(Split-Path -Leaf $installer)" -Encoding ascii
    Copy-Item -LiteralPath $buildManifestPath -Destination "$installer.build-manifest.json" -Force
    Copy-Item -LiteralPath $releaseNotes -Destination (Join-Path (Split-Path -Parent $installer) (Split-Path -Leaf $releaseNotes))
    if (-not [string]::IsNullOrWhiteSpace($PublicBaseUrl)) {
        $finalizeArguments = @{
            BundleDirectory = Split-Path -Parent $installer
            PublicBaseUrl = $PublicBaseUrl
        }
        if (-not [string]::IsNullOrWhiteSpace($ReleasePageUrl)) {
            $finalizeArguments.ReleasePageUrl = $ReleasePageUrl
        }
        & (Join-Path $PSScriptRoot "finalize_release_bundle.ps1") @finalizeArguments
    }
    Write-Host "Installer: $installer"
    Write-Host "Checksum: $installer.sha256"
    Write-Host "Build manifest: $installer.build-manifest.json"
} finally {
    Pop-Location
    Remove-GeneratedDirectory $stagingRoot (Join-Path $projectRoot "build\release-staging")
}
