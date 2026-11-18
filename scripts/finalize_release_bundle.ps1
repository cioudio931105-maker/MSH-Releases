[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BundleDirectory,
    [Parameter(Mandatory = $true)]
    [string]$PublicBaseUrl,
    [string]$ReleasePageUrl = "",
    [string]$PublishedAt = (Get-Date -Format "yyyy-MM-dd")
)

$ErrorActionPreference = "Stop"

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Assert-HttpsUrl([string]$Value, [string]$Name) {
    $uri = $null
    if (-not [Uri]::TryCreate($Value, [UriKind]::Absolute, [ref]$uri) -or $uri.Scheme -ne "https" -or
        [string]::IsNullOrWhiteSpace($uri.Host) -or $uri.UserInfo -or $uri.Query -or $uri.Fragment) {
        throw "$Name must be a public HTTPS URL without credentials, query or fragment."
    }
}

$bundle = [System.IO.Path]::GetFullPath($BundleDirectory)
if (-not (Test-Path -LiteralPath $bundle -PathType Container)) {
    throw "Release bundle directory does not exist: $bundle"
}
Assert-HttpsUrl $PublicBaseUrl "PublicBaseUrl"
$publicRoot = $PublicBaseUrl.TrimEnd("/")

$installers = @(Get-ChildItem -LiteralPath $bundle -File -Filter "MSH_Setup_v*_*.exe")
if ($installers.Count -ne 1) {
    throw "A release bundle must contain exactly one MSH installer; found $($installers.Count)."
}
$installer = $installers[0]
if ($installer.BaseName -notmatch '^MSH_Setup_v(?<version>(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?)_(?<runtime>CPU|GPU)$') {
    throw "Unexpected installer filename: $($installer.Name)"
}
$version = $Matches.version
$runtime = $Matches.runtime.ToLowerInvariant()
$checksumPath = "$($installer.FullName).sha256"
$manifestPath = "$($installer.FullName).build-manifest.json"
$releaseNotesPath = Join-Path $bundle "RELEASE_NOTES_v$version.md"
foreach ($required in @($checksumPath, $manifestPath, $releaseNotesPath)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Release bundle is incomplete; missing: $required"
    }
}
$latestPath = Join-Path $bundle "latest.json"
$recordPath = Join-Path $bundle "release-record.json"
if ((Test-Path -LiteralPath $latestPath) -or (Test-Path -LiteralPath $recordPath)) {
    throw "Refusing to overwrite finalized release evidence."
}
$allowedNames = @($installer.Name, (Split-Path -Leaf $checksumPath),
    (Split-Path -Leaf $manifestPath), (Split-Path -Leaf $releaseNotesPath))
$unexpected = @(Get-ChildItem -LiteralPath $bundle -Force | Where-Object {
    $_.PSIsContainer -or $_.Name -notin $allowedNames -or
    ($_.Attributes -band [System.IO.FileAttributes]::ReparsePoint)
})
if ($unexpected.Count -gt 0) {
    throw "Release bundle contains unexpected files or directories: $($unexpected.Name -join ', ')"
}

$actualInstallerHash = Get-Sha256 $installer.FullName
$checksumLine = (Get-Content -LiteralPath $checksumPath -Raw -Encoding ascii).Trim()
$expectedChecksumLine = "$actualInstallerHash *$($installer.Name)"
if ($checksumLine -ne $expectedChecksumLine) {
    throw "Installer checksum file does not match the installer."
}

$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding utf8 | ConvertFrom-Json
if ($manifest.version -ne $version -or $manifest.runtime -ne $runtime) {
    throw "Build manifest version/runtime does not match the installer filename."
}
if ($manifest.git_worktree_dirty -isnot [bool] -or $manifest.git_worktree_dirty -ne $false -or $manifest.build_mode -ne "release") {
    throw "Only a clean release-mode build may be finalized for publication."
}
if ($manifest.schema_version -ne 1 -or $manifest.application -ne "MSH" -or
    $manifest.git_commit -notmatch '^[0-9a-f]{40}$' -or $manifest.app_exe_sha256 -notmatch '^[0-9a-f]{64}$') {
    throw "Build manifest lacks valid application/build identity."
}
if ($manifest.model_distribution -ne "user-supplied" -or
    $null -eq $manifest.PSObject.Properties['bundled_models'] -or
    $manifest.bundled_models -isnot [System.Array] -or @($manifest.bundled_models).Count -ne 0 -or
    $manifest.bundled_research_data -isnot [bool] -or $manifest.bundled_research_data -ne $false -or
    $manifest.source_license -ne "AGPL-3.0-only") {
    throw "Only application-only builds with user-supplied models and no research data may be finalized."
}

if ([string]::IsNullOrWhiteSpace($ReleasePageUrl)) {
    $ReleasePageUrl = "$publicRoot/v$version/"
}
Assert-HttpsUrl $ReleasePageUrl "ReleasePageUrl"
$downloadUrl = "$publicRoot/v$version/$($installer.Name)"
$releaseNotes = (Get-Content -LiteralPath $releaseNotesPath -Raw -Encoding utf8).Trim()
if ([string]::IsNullOrWhiteSpace($releaseNotes)) { throw "Release notes must not be empty." }

$latest = [ordered]@{
    schema_version = 1
    version = $version
    release_name = "MSH v$version"
    release_notes = $releaseNotes
    download_url = $downloadUrl
    release_page_url = $ReleasePageUrl
    sha256 = $actualInstallerHash
    published_at = $PublishedAt
}
$latest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $latestPath -Encoding utf8

$record = [ordered]@{
    schema_version = 1
    application = "MSH"
    version = $version
    runtime = $runtime
    git_commit = $manifest.git_commit
    installer = $installer.Name
    installer_size_bytes = $installer.Length
    installer_sha256 = $actualInstallerHash
    checksum_sha256 = Get-Sha256 $checksumPath
    build_manifest_sha256 = Get-Sha256 $manifestPath
    release_notes_sha256 = Get-Sha256 $releaseNotesPath
    latest_manifest_sha256 = Get-Sha256 $latestPath
    public_base_url = $publicRoot
    model_distribution = "user-supplied"
    bundled_models = @()
    bundled_research_data = $false
    source_license = $manifest.source_license
    finalized_utc = [DateTime]::UtcNow.ToString("o")
}
$record | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $recordPath -Encoding utf8

Write-Host "Release bundle verified: $bundle"
Write-Host "Update manifest: $latestPath"
Write-Host "Release record: $recordPath"
Write-Host "Local metadata checks only; no upload, installer inspection or hardware acceptance was performed."
Write-Host "Upload the version folder once, then publish the same latest.json at the storage root."
