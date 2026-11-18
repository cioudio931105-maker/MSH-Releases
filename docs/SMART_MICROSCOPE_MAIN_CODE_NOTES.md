# 智慧化顯微鏡病理影像掃描與 AI 輔助分析系統 - 主要程式碼註解導讀

整理日期：2026-06-18  
用途：期末報告附錄、專題口頭報告、程式碼導覽

## 建議閱讀順序

1. `cell_stitching_project/config.py`：了解整個系統的設定參數。
2. `cell_stitching_project/main.py`：了解自動拼接主流程。
3. `cell_stitching_project/preprocess.py`：了解影像前處理。
4. `cell_stitching_project/alignment.py`：了解相鄰影像如何對位。
5. `cell_stitching_project/blending.py`：了解多張影像如何融合成 mosaic。
6. `cell_stitching_project/cell_identification.py`：了解 AI 偵測與標註。
7. `cell_stitching_project/detect_live.py`：了解 Basler 即時偵測。
8. `cell_stitching_project/wbc_serpentine_capture.py`：了解蛇形掃描與白血球擷取。
9. `cell_stitching_project/train_yolo_wbc400.py`：了解模型訓練入口。

## 1. 拼接設定核心：`StitchingConfig`

來源檔案：`cell_stitching_project/config.py`

```python
@dataclass(slots=True)
class StitchingConfig:
    """Runtime configuration shared by the CLI and the legacy Tkinter UI."""

    # 輸入與輸出路徑
    input_dir: str | Path
    output_dir: str | Path = Path("output")

    # 影像讀取與排序
    image_extension: str = "auto"
    input_order: Literal["auto", "natural", "coordinates"] = "auto"
    coordinate_priority: Literal["row-major", "column-major"] = "row-major"

    # 影像拼接方法
    alignment_method: str = "auto"
    blending_method: str = "auto"
    overlap_ratio: float = 0.40

    # 影像前處理
    use_grayscale: bool = True
    use_denoise: bool = True
    use_clahe: bool = True
    use_flatfield: bool = True

    # AI 輔助對位與拼接後偵測
    use_yolo_guidance: bool = False
    yolo_model_path: str | None = None
    post_stitch_detection_enabled: bool = True

    # 效能與硬體設定
    prefer_gpu: bool = True
    compute_device: Literal["auto", "cuda", "cpu"] = "auto"
    gpu_fallback_allowed: bool = True
    performance_profile: Literal["quality", "balanced", "resource"] = "balanced"
```

說明：

- `input_dir` 與 `output_dir` 決定拼接輸入與輸出位置。
- `alignment_method` 可指定 phase、ECC、ORB、SIFT，也可使用 auto。
- `use_yolo_guidance` 啟用後，系統會使用 AI 偵測到的細胞區域幫助對位。
- `post_stitch_detection_enabled` 啟用後，拼接完成會自動對結果圖做 AI 偵測。
- `compute_device` 與 `gpu_fallback_allowed` 讓系統可在 GPU 失敗時回到 CPU，增加穩定性。

## 2. 自動拼接主流程：`run_stitch_pipeline()`

來源檔案：`cell_stitching_project/main.py`

```python
def run_stitch_pipeline(config: StitchingConfig) -> StitchingResult:
    """Run the full stitching pipeline and return artifact paths for CLI or UI usage."""

    # 1. 建立輸出資料夾、log、debug 目錄
    output_paths = create_output_paths(...)
    logger = configure_logger(output_paths.log_path)

    # 2. 偵測目前 runtime，例如 CUDA、GPU、OpenCV CUDA、YOLO device
    config.runtime = probe_runtime(...)

    # 3. 收集並排序輸入影像
    image_paths = list_image_paths(...)
    if len(image_paths) < 2:
        raise RuntimeError("At least two valid images are required for stitching.")

    # 4. 大量影像時啟用 streaming mode，降低記憶體壓力
    streaming_mode = _should_use_streaming_mode(len(image_paths))

    # 5. 可選擇使用 YOLO guidance 產生 ROI mask，幫助顯微鏡影像對位
    detector = YoloGuidance(...) if config.use_yolo_guidance else None

    # 6. 前處理與相鄰影像對位
    #    小批量：一次載入並處理
    #    大批量：逐張 streaming 處理
    pairwise = []
    for index in range(len(processed) - 1):
        result = estimate_pairwise_shift(processed[index], processed[index + 1], config)
        pairwise.append(result)

    # 7. 根據位移結果建立每張 tile 在大圖上的位置
    placements, canvas = build_layout(...)

    # 8. 自動選擇融合方法並輸出 mosaic
    config.blending_method = _resolve_blending_method(config, canvas, len(image_paths))
    blended, blend_warnings = blend_tiles(...)

    # 9. 拼接後再執行 AI 偵測
    post_detection = _run_post_stitch_detection(...)

    # 10. 保存影像、CSV、JSON、debug 圖
    save_image(output_paths.result_path, blended)
    save_shift_records_csv(...)
    save_json(...)

    # 11. 回傳所有重要輸出路徑
    return StitchingResult(...)
```

說明：

- 這是整個拼接系統的總控函式。
- 它把影像讀取、前處理、對位、排版、融合、後處理偵測與輸出全部串起來。
- `StitchingResult` 會記錄結果圖、預覽圖、位移 JSON/CSV、debug 資料夾與 warning。

## 3. 影像前處理：`preprocess_image()`

來源檔案：`cell_stitching_project/preprocess.py`

```python
def preprocess_image(path: Path, image_bgr: np.ndarray, config: StitchingConfig) -> PreprocessedImage:
    """Generate the alignment grayscale image and the blend-ready image."""

    # 如果目前 runtime 是 CUDA，先嘗試 GPU 前處理
    if config.runtime is not None and config.runtime.device == "cuda":
        try:
            return _preprocess_on_gpu(Path(path), image_bgr, config)
        except Exception as exc:
            # GPU 前處理失敗時，如果允許 fallback，就改用 CPU
            if not config.gpu_fallback_allowed:
                raise
            config.record_fallback("preprocess", str(exc), "cuda", "cpu")

    # 建立彩色影像與灰階影像
    blend_image = image_bgr.copy()
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

    # 修正顯微鏡照明不均
    if config.use_flatfield:
        gray = _flatfield_gray(gray, config.flatfield_sigma_ratio)
        blend_image = _flatfield_bgr(blend_image, config.flatfield_sigma_ratio)

    # 降噪，減少細胞背景雜訊對對位的影響
    if config.use_denoise:
        gray = cv2.fastNlMeansDenoising(gray, None, h=float(max(1, config.denoise_strength)))

    # CLAHE 提升局部對比，讓細胞邊界更明顯
    if config.use_clahe:
        clahe = cv2.createCLAHE(...)
        gray = clahe.apply(gray)

    # 只縮小對位用灰階圖，不犧牲最終拼接輸出解析度
    alignment_gray, alignment_scale_x, alignment_scale_y = _resize_alignment_gray(...)

    return PreprocessedImage(...)
```

說明：

- `alignment_gray` 是給演算法估位移用的影像。
- `blend_bgr` 是最後融合用的彩色影像。
- 這樣可以同時兼顧對位速度與輸出品質。

## 4. 相鄰影像對位：`estimate_pairwise_shift()`

來源檔案：`cell_stitching_project/alignment.py`

```python
def estimate_pairwise_shift(
    ref_tile: PreprocessedImage,
    mov_tile: PreprocessedImage,
    config: StitchingConfig,
    logger: Any | None = None,
) -> AlignmentResult:
    """Estimate the relative translation of two neighboring images."""

    # 如果兩張影像都有 YOLO guidance mask，優先嘗試使用 ROI 對位
    guidance_modes = [False]
    if config.use_yolo_guidance and ref_tile.guidance_mask is not None and mov_tile.guidance_mask is not None:
        guidance_modes = [True, False]

    # 若檔名含座標，可推論下一張圖應該在右、左、上、下哪個方向
    direction_hint = _infer_direction_hint(ref_tile.path.stem, mov_tile.path.stem)

    for guided in guidance_modes:
        ref_mask = ref_tile.guidance_mask if guided else None
        mov_mask = mov_tile.guidance_mask if guided else None

        # auto 模式下會依序嘗試 phase、ECC、ORB、SIFT 等方法
        for method in _method_chain(config.alignment_method):
            candidates = _candidate_views(...)

            # 若有方向提示，只保留合理方向的候選重疊區
            if direction_hint is not None:
                candidates = [candidate for candidate in candidates if candidate["direction"] == direction_hint]

            for candidate in candidates:
                if method == "phase":
                    local_dx, local_dy, angle, score = _estimate_phase_cpu(...)
                elif method == "ecc":
                    local_dx, local_dy, angle, score = _estimate_ecc(...)
                else:
                    local_dx, local_dy, angle, score, matches_image = _estimate_feature(...)

                # 把局部 strip 估到的位移轉回原圖尺度
                result = AlignmentResult(
                    dx=(candidate["base_dx"] + local_dx) * ref_tile.alignment_scale_x,
                    dy=(candidate["base_dy"] + local_dy) * ref_tile.alignment_scale_y,
                    method=method,
                    direction=candidate["direction"],
                    used_yolo_guidance=guided,
                )

                # 過濾不合理位移，例如超出最大相對移動量
                if _validate_candidate(result, width, height, config):
                    return result

    return AlignmentResult(success=False, error="No valid alignment candidate")
```

說明：

- 對位的目標是找出下一張 tile 相對於前一張 tile 的 `dx` 與 `dy`。
- 使用方向提示與 ROI mask 可以降低顯微鏡影像背景重複造成的誤配。
- 若 GPU phase 失敗且允許 fallback，系統會改用 CPU phase。

## 5. 影像融合：`blend_tiles()`

來源檔案：`cell_stitching_project/blending.py`

```python
def blend_tiles(
    images: list[np.ndarray],
    placements: list[TilePlacement],
    canvas: CanvasLayout,
    config: StitchingConfig,
) -> tuple[np.ndarray, list[str]]:
    """Blend all tiles into a single mosaic."""

    if not images:
        raise ValueError("No images provided for blending")

    # 優先使用 GPU 融合，加速大圖處理
    if config.runtime is not None and config.runtime.device == "cuda":
        try:
            return _blend_tiles_gpu(images, placements, canvas, config)
        except Exception as exc:
            # GPU 失敗時回到 CPU，避免整個流程中斷
            if not config.gpu_fallback_allowed:
                raise
            config.record_fallback("blend", str(exc), "cuda", "cpu")

    return _blend_tiles_cpu(images, placements, canvas, config)
```

說明：

- `placements` 告訴系統每張 tile 要放到 canvas 的哪個位置。
- `canvas` 記錄最後大圖的寬、高與原點偏移。
- `feather` 與 `multiband` 可以讓重疊區更平滑。

## 6. AI 細胞偵測封裝：`CellIdentificationDetector`

來源檔案：`cell_stitching_project/cell_identification.py`

```python
class CellIdentificationDetector:
    def __init__(self, model_path, backend=None, class_names=None, confidence=0.35, ...):
        self.model_path = Path(model_path)
        self.backend = (backend or self._infer_backend(self.model_path)).lower()

        if self.backend == "ultralytics":
            # .pt 模型使用 Ultralytics YOLO
            YOLO = _import_ultralytics()
            self.model = YOLO(str(self.model_path))
            self.class_names = class_names or _normalize_class_names(self.model.names)

        elif self.backend == "onnx":
            # .onnx 模型使用 ONNX Runtime
            self.session, self.providers = _create_onnx_session(...)
            self.input_name = self.session.get_inputs()[0].name

        else:
            raise ValueError("backend must be 'ultralytics' or 'onnx'")

    def predict(self, frame: np.ndarray) -> list[CellDetection]:
        # 對外提供同一個 predict 介面，不讓呼叫端關心 backend
        if self.backend == "onnx":
            return self._predict_onnx(frame)
        return self._predict_ultralytics(frame)
```

說明：

- 此類別把不同模型格式統一成相同推論介面。
- 回傳結果使用 `CellDetection`，因此後續畫框、輸出 JSON、裁切 ROI 都能共用。

## 7. 離線偵測主流程：`run_cell_identification()`

來源檔案：`cell_stitching_project/cell_identification.py`

```python
def run_cell_identification(config: CellIdentificationConfig) -> CellIdentificationResult:
    # 收集單張影像或整個資料夾中的所有影像
    image_paths = collect_image_paths(config.source)

    # 載入 class names，若沒有提供 class file，預設使用五分類 WBC
    class_names = load_class_names(config.class_file) if config.class_file is not None else None

    # 建立 detector
    detector = CellIdentificationDetector(...)

    # 對每張影像做推論、畫框、保存標註圖
    results = []
    for image_path in image_paths:
        detections, annotated = detector.predict_image(image_path)
        save_image(output_path, annotated)
        results.append({
            "image": str(image_path.resolve()),
            "annotated_image": str(output_path.resolve()),
            "detections": [detection.to_dict() for detection in detections],
        })

    # 統計各類別數量並輸出 JSON
    payload = {
        "model": str(config.model_path.resolve()),
        "backend": detector.backend,
        "images_processed": len(results),
        "total_detections": total_detections,
        "label_counts": label_counts,
        "results": results,
    }
    save_json(json_output, payload)

    return CellIdentificationResult(...)
```

說明：

- 適合用於報告中的實驗結果整理。
- JSON 中有每張圖的 bounding box、confidence 與類別，可進一步做統計圖表。

## 8. 即時偵測流程：`detect_live.py`

來源檔案：`cell_stitching_project/detect_live.py`

```python
def process_frame(frame, detector, session_paths, frame_index, save_crops, save_frames, stabilizer=None):
    # 對目前 frame 做 AI 偵測
    detections = detector.predict(frame)

    # 統計每個 label 的數量
    counts = count_labels(detections)

    # 若啟用穩定判斷，使用最近 N 個 frame 投票
    stable_decision = stabilizer.update(detections) if stabilizer is not None else None

    # 可選擇保存偵測到的 ROI crop
    crop_records = save_detection_crops(...) if save_crops else []

    # 可選擇保存已畫框的 frame
    if save_frames:
        annotated = draw_count_overlay(draw_detections(frame, detections), counts)
        save_image(frame_path, annotated)

    return detections, counts, event
```

主迴圈概念：

```python
with BaslerCamera(camera_config) as camera:
    while True:
        # 1. 從 Basler 相機讀取 frame
        frame = camera.read()

        # 2. 推論並建立 event
        detections, counts, event = process_frame(...)

        # 3. 若穩定事件成立，寫入 stable_events.jsonl 或送出 serial command
        emitted_event = event_dispatcher.handle(...)

        # 4. 顯示即時預覽，使用者可按 q 離開、s 手動保存、r 重新載入 label
        cv2.imshow("Basler Live Detection", preview)
```

說明：

- 即時流程適合專題展示，因為畫面會顯示偵測框、數量、FPS 與推論時間。
- `DetectionStabilizer` 可以避免一兩張 frame 的錯誤偵測直接觸發硬體動作。

## 9. 白血球蛇形掃描擷取：`run_serpentine_white_blood_cell_capture()`

來源檔案：`cell_stitching_project/wbc_serpentine_capture.py`

```python
def run_serpentine_white_blood_cell_capture() -> Path:
    # 建立輸出資料夾
    output_dir = Path(DEFAULT_CONFIG["output_root"]) / WHITE_BLOOD_CELL_CLASS / experiment_name / date_time
    output_dir.mkdir(parents=True, exist_ok=True)

    # 產生垂直蛇形掃描路徑
    path = generate_vertical_serpentine_path()
    camera = start_live_camera()

    for coord in path:
        # 1. 移動 stage 到指定座標
        current_x = int(coord["x"])
        current_y = int(coord["y"])
        move_to_coordinate(current_x, current_y)

        # 2. 讀取 preview frame，直到偵測到可停止掃描的 WBC
        frame, preview_detections, scan_stop_preview = read_preview_until_scan_stop(...)

        # 3. 若偵測到 WBC，停止 stage
        _get_stage().stop()

        # 4. 嘗試將 WBC 移動到畫面中央
        current_x, current_y, frame, preview_detections, centered = center_white_blood_cell_for_high_magnification(...)

        # 5. 提示使用者切換 1000x 並對焦
        wait_for_manual_capture_confirmation()

        # 6. 拍攝高倍率影像
        high_res = capture_high_resolution_image()
        original_path = save_original_frame(high_res, current_x, current_y, output_dir)

        # 7. 偵測高倍率影像中的 WBC，裁切並寫 metadata.csv
        high_res_detections = detect_white_blood_cells(high_res)
        for det in high_res_detections:
            crop_img = crop_white_blood_cell_by_bbox(high_res, det.bbox, ...)
            crop_path = save_white_blood_cell_crop(...)
            write_metadata_csv(...)

        # 8. 使用者切回 400x 後繼續掃描
        wait_for_resume_confirmation()

    _write_summary(output_dir, len(path))
    return output_dir
```

說明：

- 此流程把低倍率搜尋與高倍率擷取結合。
- `metadata.csv` 是非常重要的成果，因為它把座標、類別、confidence、bbox、原圖與 crop 路徑全部記錄下來。

## 10. 模型訓練入口：`train_yolo_wbc400.py`

來源檔案：`cell_stitching_project/train_yolo_wbc400.py`

```python
def train_wbc400(args: argparse.Namespace) -> Path | None:
    # 1. 檢查 data.yaml 是否存在
    data_yaml = Path(args.data)
    if not data_yaml.exists():
        raise FileNotFoundError(f"Data yaml not found: {data_yaml}")

    # 2. 驗證類別名稱是否符合 WBC 五分類或 WBC-only 設定
    class_names = validate_wbc_data_yaml(...)

    # 3. 設定 Ultralytics YOLO 訓練參數
    train_kwargs = {
        "data": str(data_yaml),
        "epochs": int(args.epochs),
        "imgsz": int(args.imgsz),
        "batch": int(args.batch),
        "optimizer": str(args.optimizer),
        "lr0": float(args.lr0),
        "mosaic": float(args.mosaic),
        "mixup": float(args.mixup),
        "degrees": float(args.degrees),
        "single_cls": bool(args.single_cls or args.wbc_only),
    }

    # 4. dry-run 可只檢查參數，不真的訓練
    if args.dry_run:
        print(f"classes={class_names}")
        print(f"train_kwargs={train_kwargs}")
        return None

    # 5. 載入 YOLO base model 並開始訓練
    model = YOLO(model_arg)
    result = model.train(**train_kwargs)
    return Path(result.save_dir)
```

說明：

- 這個檔案讓專案能持續針對自己的顯微鏡影像重新訓練模型。
- `imgsz=1280` 是為了保留 400x 細胞形態細節。
- `degrees=180`、`flipud=0.5`、`fliplr=0.5` 有助於處理細胞旋轉方向不固定的問題。

## 11. 報告可用的核心流程摘要

可直接放在簡報或報告中的短版說明：

```text
本系統先透過 Basler 或 OpenCV camera 取得顯微鏡影像，再對影像進行平場校正、去雜訊與 CLAHE 對比增強。接著利用 phase correlation、ECC、ORB 或 SIFT 計算相鄰影像位移，建立整體 canvas layout 並使用 feather 或 multiband blending 產生完整 mosaic。拼接完成後，系統會使用 YOLO 或 ONNX 模型自動偵測細胞，輸出標註影像、JSON、CSV 與偵錯資料。若使用蛇形掃描模式，系統可在低倍率下搜尋白血球，偵測到目標後暫停載物台、將白血球置中，提示使用者切換高倍率拍攝並保存裁切影像與 metadata。
```

## 12. 主要檔案功能表

| 檔案 | 功能 |
|---|---|
| `config.py` | 拼接、偵測與 runtime 設定 |
| `main.py` | 自動拼接主流程 |
| `preprocess.py` | 平場校正、降噪、CLAHE、對位圖縮放 |
| `alignment.py` | phase/ECC/ORB/SIFT 對位 |
| `blending.py` | average/feather/multiband 融合 |
| `cell_identification.py` | YOLO/ONNX 離線偵測與標註 |
| `detect_live.py` | Basler 即時偵測與穩定事件 |
| `camera/basler.py` | Basler 相機存取封裝 |
| `serpentine_recording.py` | 蛇形掃描錄影 |
| `wbc_serpentine_capture.py` | WBC 掃描、置中、高倍率擷取與裁切 |
| `coordinate_overlay_stitch.py` | 座標式拼接與內容式修正 |
| `train_yolo_wbc400.py` | WBC YOLO 訓練入口 |
| `prepare_wbc400_wbc_only_dataset.py` | WBC-only 訓練資料集產生 |
| `verify_environment.py` | 軟體環境檢查 |
| `hardware_preflight.py` | 硬體與 launcher 預檢 |
