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
    if (-not [Uri]::TryCreate($Value, [UriKind]::Absolute, [ref]$uri) -or $uri.Scheme -ne "https") {
        throw "$Name must be an absolute HTTPS URL: $Value"
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
if ($installer.BaseName -notmatch '^MSH_Setup_v(?<version>\d+\.\d+\.\d+(?:[-.][0-9A-Za-z.-]+)?)_(?<runtime>CPU|GPU)$') {
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
if ($manifest.git_worktree_dirty -ne $false -or $manifest.build_mode -ne "release") {
    throw "Only a clean release-mode build may be finalized for publication."
}

if ([string]::IsNullOrWhiteSpace($ReleasePageUrl)) {
    $ReleasePageUrl = "$publicRoot/v$version/"
}
Assert-HttpsUrl $ReleasePageUrl "ReleasePageUrl"
$downloadUrl = "$publicRoot/v$version/$($installer.Name)"
$releaseNotes = (Get-Content -LiteralPath $releaseNotesPath -Raw -Encoding utf8).Trim()

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
$latestPath = Join-Path $bundle "latest.json"
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
    finalized_utc = [DateTime]::UtcNow.ToString("o")
}
$recordPath = Join-Path $bundle "release-record.json"
$record | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $recordPath -Encoding utf8

Write-Host "Release bundle verified: $bundle"
Write-Host "Update manifest: $latestPath"
Write-Host "Release record: $recordPath"
Write-Host "Upload the version folder once, then publish the same latest.json at the storage root."
