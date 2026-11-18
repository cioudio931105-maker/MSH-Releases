# Training With User-Captured Slides

## 1) Prepare your upload structure

Place your new images under one folder with class subfolders:

```text
<new_data_root>/
  class_a/
    img001.jpg
    img002.jpg
  class_b/
    img101.jpg
  class_c/
    ...
```

## 2) Domain-adaptation training (recommended)

Use your new images as the focus domain, and optionally mix old data:

```powershell
python scripts/train_domain_adapt.py `
  --new_data "data/my_new_slides" `
  --legacy_data "data/cell_images_classification" `
  --output_dataset "data/dataset_domain_adapt" `
  --new_weight 3 `
  --epochs 100 `
  --imgsz 224 `
  --batch 16 `
  --name "domain_adapt_v1"
```

Notes:
- `--new_weight 3` means your new slide images are oversampled to reduce domain gap.
- leave `--legacy_data` empty if you only want to train on new data.

## 3) Dataset-only check (no training)

```powershell
python scripts/train_domain_adapt.py `
  --new_data "data/my_new_slides" `
  --prepare_only
```

## 4) Output

Training outputs are saved under:

```text
runs/classify/<name>/
  weights/best.pt
  weights/last.pt
```

Use `weights/best.pt` as the preferred model.
