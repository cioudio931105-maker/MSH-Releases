# Offline Cell Analysis Pipeline

This project analyzes microscope scan videos after recording is complete.

Pipeline:

1. Read microscope video.
2. Extract frames by frame interval or time interval.
3. Skip blurry frames using Laplacian variance.
4. Run YOLOv8 detection for RBC, WBC, and Platelet.
5. Save bbox CSV outputs.
6. Assign simple tracks to remove repeated cells.
7. Crop unique cell ROIs into class folders.
8. Write summary statistics.

Directory layout:

```text
offline_cell_analysis/
  videos/
  extracted_frames/
  detections/
  cropped_cells/
  models/
  outputs/
  main.py
```

Example:

```powershell
cd C:\Cell_Project\Cell_Project\offline_cell_analysis
python main.py --video videos\scan.mp4 --model models\blood_cells_3cls.pt --every-n-frames 5 --conf 0.25 --blur-threshold 80 --device cuda --batch-size 8 --save-annotated
```

Time-based extraction:

```powershell
python main.py --video videos\scan.mp4 --model models\blood_cells_3cls.pt --every-seconds 0.5 --conf 0.25 --device cuda
```

CPU fallback:

```powershell
python main.py --video videos\scan.mp4 --model models\blood_cells_3cls.pt --every-n-frames 5 --device cpu
```

Main outputs:

```text
outputs/<run>/frames_manifest.csv
detections/<run>/detections_all.csv
detections/<run>/detections_tracked.csv
detections/<run>/unique_cells.csv
detections/<run>/tracks.csv
cropped_cells/<run>/RBC/
cropped_cells/<run>/WBC/
cropped_cells/<run>/Platelet/
outputs/<run>/summary.json
```

Continue training the 3-class model from offline detections:

```powershell
cd C:\Cell_Project\Cell_Project\offline_cell_analysis
python train_three_class_from_detections.py --min-conf 0.65 --epochs 30 --batch 2 --imgsz 960 --device cpu
```

This command uses the latest `detections/<run>/detections_all.csv` by default, keeps only high-confidence
WBC/RBC/Platelet pseudo labels, writes a YOLO dataset under `training_datasets/`, and continues training from
the existing 3-class model. To only prepare the dataset without training:

```powershell
python train_three_class_from_detections.py --prepare-only --min-conf 0.65
```

Double-click option:

```text
offline_cell_analysis/train_three_class_model.bat
```

Recommended starting values:

```text
every-n-frames: 5 to 10
conf: 0.25
blur-threshold: 60 to 120
duplicate-iou: 0.35
duplicate-centroid: 80
track-gap: 8
crop-margin: 0.10
```
