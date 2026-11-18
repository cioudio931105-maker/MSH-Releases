[CmdletBinding()]
param(
    [Parameter()]
    [string]$BackupRoot = 'D:\Microscope-Scanner-Helper_MSH_BACKUP_2026_08_17',

    [Parameter()]
    [string]$DestinationRoot = (Join-Path (Split-Path -Parent $PSScriptRoot) 'data\training\doctor_blood_smear_20260821')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$imageExtensions = @('.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff')

if (-not (Test-Path -LiteralPath $BackupRoot -PathType Container)) {
    throw "Cold backup was not found: $BackupRoot"
}

if (Test-Path -LiteralPath $DestinationRoot) {
    throw "Destination already exists; refusing to overwrite research data: $DestinationRoot"
}

New-Item -ItemType Directory -Path $DestinationRoot | Out-Null

function Copy-DatasetFolder {
    param(
        [Parameter(Mandatory)] [string]$Source,
        [Parameter(Mandatory)] [string]$Name,
        [Parameter(Mandatory)] [string]$Status
    )

    if (-not (Test-Path -LiteralPath $Source -PathType Container)) {
        throw "Required dataset folder was not found: $Source"
    }

    $target = Join-Path $DestinationRoot $Name
    New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
    Copy-Item -LiteralPath $Source -Destination $target -Recurse
    return [PSCustomObject]@{ Source = $Source; Destination = $target; Status = $Status }
}

$manifest = [System.Collections.Generic.List[object]]::new()

# Original full-resolution microscope frames: doctor annotation input.
$capturedRoot = Join-Path $BackupRoot 'stitched_output\stitched_output\stitched_output\captured'
$rawTarget = Join-Path $DestinationRoot '01_raw_blood_smear_images_to_annotate'
New-Item -ItemType Directory -Path $rawTarget | Out-Null

$sessions = Get-ChildItem -LiteralPath $capturedRoot -Directory -Filter 'manual_session_*'
foreach ($session in $sessions) {
    $rawImages = Get-ChildItem -LiteralPath $session.FullName -File |
        Where-Object { $imageExtensions -contains $_.Extension.ToLowerInvariant() }
    foreach ($image in $rawImages) {
        $targetName = "$($session.Name)__$($image.Name)"
        $targetPath = Join-Path $rawTarget $targetName
        Copy-Item -LiteralPath $image.FullName -Destination $targetPath
        $manifest.Add([PSCustomObject]@{
            group = 'raw_for_doctor_annotation'
            status = 'unlabeled_original_frame'
            source = $image.FullName
            copied_to = $targetPath
            class_schema = ''
        })
    }
}

$datasets = @(
    @{ RelativePath = 'staging\confidence_boost_3cls\latest'; Target = '02_yolo_3cls_existing_labels_review_required\confidence_boost_3cls'; Status = 'existing_labels_require_physician_review'; Schema = '0=WBC; 1=RBC; 2=Platelets' },
    @{ RelativePath = 'staging\wbc_boost_3cls\latest'; Target = '02_yolo_3cls_existing_labels_review_required\wbc_boost_3cls'; Status = 'existing_labels_require_physician_review'; Schema = '0=WBC; 1=RBC; 2=Platelets' },
    @{ RelativePath = 'datasets\TXL-PBC_Dataset\TXL-PBC'; Target = '03_external_txl_pbc_reference_license_review\TXL-PBC'; Status = 'external_reference_verify_license_before_redistribution'; Schema = '0=WBC; 1=RBC; 2=Platelets' },
    @{ RelativePath = 'datasets\wbc5_classification_1000x_smoke'; Target = '04_wbc5_reference_smoke_only'; Status = 'small_reference_not_training_ready'; Schema = 'neutrophil; lymphocyte; monocyte; eosinophil; basophil' }
)

foreach ($dataset in $datasets) {
    $source = Join-Path $BackupRoot $dataset.RelativePath
    $copied = Copy-DatasetFolder -Source $source -Name $dataset.Target -Status $dataset.Status
    $manifest.Add([PSCustomObject]@{
        group = $dataset.Target
        status = $dataset.Status
        source = $copied.Source
        copied_to = $copied.Destination
        class_schema = $dataset.Schema
    })
}

$manifest | Export-Csv -LiteralPath (Join-Path $DestinationRoot 'DATASET_MANIFEST.csv') -NoTypeInformation -Encoding utf8

$readme = @"
# Blood-smear annotation and AI-training package

Created from cold backup: $BackupRoot

## Folder meaning

- `01_raw_blood_smear_images_to_annotate`: original microscope frames for physician annotation. Do not use generated detection overlays or crops as ground truth.
- `02_yolo_3cls_existing_labels_review_required`: existing YOLO-format labels for WBC/RBC/Platelets. These are candidate labels and must be reviewed before retraining.
- `03_external_txl_pbc_reference_license_review`: externally sourced reference set. Confirm its licence and permitted use before redistribution or publication.
- `04_wbc5_reference_smoke_only`: a small five-WBC-class reference set; it is not large enough to train or validate a clinical model.

## Required physician review

For every accepted image: confirm the bounding boxes, correct the class, add missed cells, and mark unusable images. Maintain patient/slide separation when making train, validation, and test splits. Do not mix images from one slide across splits.

The CSV manifest records provenance and status. This folder is Git-ignored and intentionally stays local.
"@
Set-Content -LiteralPath (Join-Path $DestinationRoot 'README.md') -Value $readme -Encoding utf8

Write-Host "Prepared local dataset package: $DestinationRoot"
Write-Host "Raw original frames copied: $((Get-ChildItem -LiteralPath $rawTarget -File).Count)"
Write-Host "Manifest: $(Join-Path $DestinationRoot 'DATASET_MANIFEST.csv')"
