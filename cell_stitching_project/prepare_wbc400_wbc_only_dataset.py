from __future__ import annotations

import argparse
import csv
import json
import random
import shutil
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np

from .io_utils import read_image, save_image, save_json


ZENODO_RECORD_API = "https://zenodo.org/api/records/14277609"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
DEFAULT_MLL23_CLASSES = ("lymphocyte_reactive",)
COMMON_WBC_MLL23_CLASSES = (
    "basophil",
    "eosinophil",
    "lymphocyte",
    "lymphocyte_large_granular",
    "lymphocyte_neoplastic",
    "lymphocyte_reactive",
    "monocyte",
    "neutrophil_band",
    "neutrophil_segmented",
)


@dataclass(frozen=True, slots=True)
class AnchorSample:
    session: str
    image_path: Path
    label_path: Path
    image_width: int
    image_height: int
    boxes_xyxy: tuple[tuple[int, int, int, int], ...]

    @property
    def box_sizes(self) -> tuple[tuple[int, int], ...]:
        return tuple((x2 - x1, y2 - y1) for x1, y1, x2, y2 in self.boxes_xyxy)


@dataclass(frozen=True, slots=True)
class CropSource:
    path: Path
    class_name: str


def workspace_root() -> Path:
    return Path(__file__).resolve().parents[1]


def preferred_work_root() -> Path:
    d_root = Path("D:/")
    if d_root.exists():
        return Path("D:/Cell_Project_training_staging")
    return workspace_root() / "staging"


def preferred_dataset_root() -> Path:
    d_root = Path("D:/")
    if d_root.exists():
        return Path("D:/Cell_Project_Datasets")
    return workspace_root() / "external"


def default_anchor_session() -> Path:
    return (
        workspace_root()
        / "stitched_output"
        / "stitched_output"
        / "stitched_output"
        / "captured"
        / "manual_session_20260617_100926_956369"
    )


def default_mll23_root() -> Path:
    return preferred_dataset_root() / "MLL23"


def default_output_root() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return preferred_work_root() / "wbc400_wbc_only" / stamp


def parse_class_list(value: str | Iterable[str]) -> tuple[str, ...]:
    if isinstance(value, str):
        names = [item.strip() for item in value.split(",") if item.strip()]
    else:
        names = [str(item).strip() for item in value if str(item).strip()]
    expanded: list[str] = []
    for name in names:
        if name == "common":
            expanded.extend(COMMON_WBC_MLL23_CLASSES)
        elif name == "quick":
            expanded.extend(DEFAULT_MLL23_CLASSES)
        else:
            expanded.append(name.removesuffix(".zip"))
    return tuple(dict.fromkeys(expanded))


def _read_zenodo_record(api_url: str = ZENODO_RECORD_API) -> dict[str, object]:
    with urllib.request.urlopen(api_url, timeout=60) as response:
        return json.load(response)


def _zenodo_file_map(api_url: str = ZENODO_RECORD_API) -> dict[str, dict[str, object]]:
    record = _read_zenodo_record(api_url)
    files = record.get("files", [])
    if not isinstance(files, list):
        raise ValueError("Zenodo record has no file list.")
    file_map: dict[str, dict[str, object]] = {}
    for file_info in files:
        if not isinstance(file_info, dict):
            continue
        key = str(file_info.get("key", ""))
        if key:
            file_map[key] = file_info
    return file_map


def download_mll23_archives(
    mll23_root: Path,
    class_names: Iterable[str],
    *,
    api_url: str = ZENODO_RECORD_API,
    overwrite: bool = False,
) -> list[Path]:
    mll23_root.mkdir(parents=True, exist_ok=True)
    file_map = _zenodo_file_map(api_url)
    downloaded: list[Path] = []
    for class_name in parse_class_list(class_names):
        archive_name = f"{class_name}.zip"
        file_info = file_map.get(archive_name)
        if file_info is None:
            available = ", ".join(sorted(file_map))
            raise ValueError(f"MLL23 archive not found: {archive_name}. Available: {available}")
        links = file_info.get("links", {})
        if not isinstance(links, dict) or "self" not in links:
            raise ValueError(f"MLL23 archive has no download link: {archive_name}")
        destination = mll23_root / archive_name
        if destination.exists() and not overwrite:
            downloaded.append(destination)
            continue
        with urllib.request.urlopen(str(links["self"]), timeout=120) as response, destination.open("wb") as handle:
            shutil.copyfileobj(response, handle)
        downloaded.append(destination)
    return downloaded


def extract_archives(archives: Iterable[Path], mll23_root: Path, *, overwrite: bool = False) -> list[Path]:
    extracted: list[Path] = []
    for archive in archives:
        class_dir = mll23_root / archive.stem
        if class_dir.exists() and any(class_dir.iterdir()) and not overwrite:
            extracted.append(class_dir)
            continue
        if class_dir.exists():
            shutil.rmtree(class_dir)
        class_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as zip_handle:
            zip_handle.extractall(class_dir)
        extracted.append(class_dir)
    return extracted


def _yolo_row_to_xyxy(row: str, width: int, height: int) -> tuple[int, int, int, int] | None:
    parts = row.split()
    if len(parts) != 5:
        raise ValueError(f"Invalid YOLO row: {row}")
    class_id = int(float(parts[0]))
    if class_id != 0:
        return None
    cx, cy, box_w, box_h = (float(value) for value in parts[1:])
    x1 = int(round((cx - box_w / 2.0) * width))
    y1 = int(round((cy - box_h / 2.0) * height))
    x2 = int(round((cx + box_w / 2.0) * width))
    y2 = int(round((cy + box_h / 2.0) * height))
    return max(0, x1), max(0, y1), min(width, x2), min(height, y2)


def load_anchor_samples(anchor_session: Path) -> list[AnchorSample]:
    training_dir = anchor_session / "training_dataset"
    images_dir = training_dir / "images"
    labels_dir = training_dir / "labels"
    if not images_dir.is_dir() or not labels_dir.is_dir():
        raise FileNotFoundError(f"Anchor session has no training_dataset images/labels: {anchor_session}")

    samples: list[AnchorSample] = []
    for image_path in sorted(path for path in images_dir.iterdir() if path.suffix.lower() in IMAGE_EXTENSIONS):
        label_path = labels_dir / f"{image_path.stem}.txt"
        if not label_path.is_file():
            continue
        image = read_image(image_path)
        height, width = image.shape[:2]
        boxes: list[tuple[int, int, int, int]] = []
        for row in label_path.read_text(encoding="utf-8").splitlines():
            stripped = row.strip()
            if not stripped:
                continue
            box = _yolo_row_to_xyxy(stripped, width=width, height=height)
            if box is not None:
                x1, y1, x2, y2 = box
                if x2 > x1 and y2 > y1:
                    boxes.append(box)
        if boxes:
            samples.append(
                AnchorSample(
                    session=anchor_session.name,
                    image_path=image_path,
                    label_path=label_path,
                    image_width=width,
                    image_height=height,
                    boxes_xyxy=tuple(boxes),
                )
            )
    if not samples:
        raise ValueError(f"No WBC anchor boxes were found in: {anchor_session}")
    return samples


def anchor_target_size(samples: Iterable[AnchorSample]) -> tuple[int, int]:
    widths: list[int] = []
    heights: list[int] = []
    for sample in samples:
        for width, height in sample.box_sizes:
            widths.append(width)
            heights.append(height)
    if not widths or not heights:
        raise ValueError("No anchor box sizes available.")
    return int(round(float(np.median(widths)))), int(round(float(np.median(heights))))


def discover_mll23_crops(
    mll23_root: Path,
    class_names: Iterable[str],
    *,
    max_per_class: int | None = None,
) -> list[CropSource]:
    selected = set(parse_class_list(class_names))
    crops: list[CropSource] = []
    for class_name in sorted(selected):
        candidates: list[Path] = []
        preferred_dir = mll23_root / class_name
        search_roots = [preferred_dir] if preferred_dir.is_dir() else [mll23_root]
        for search_root in search_roots:
            if not search_root.exists():
                continue
            for path in sorted(search_root.rglob("*")):
                if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
                    path_parts = {part.lower() for part in path.parts}
                    if class_name.lower() in path_parts or path.stem.lower().startswith(class_name.lower()):
                        candidates.append(path)
        if max_per_class is not None:
            candidates = candidates[: max(0, int(max_per_class))]
        crops.extend(CropSource(path=path, class_name=class_name) for path in candidates)
    return crops


def _make_cell_mask(crop: np.ndarray) -> np.ndarray:
    h, w = crop.shape[:2]
    central_prior = np.zeros((h, w), dtype=np.uint8)
    cv2.ellipse(
        central_prior,
        (w // 2, h // 2),
        (max(4, int(w * 0.42)), max(4, int(h * 0.42))),
        0,
        0,
        360,
        255,
        -1,
    )
    border_width = max(4, min(h, w) // 12)
    border = np.concatenate(
        [
            crop[:border_width].reshape(-1, 3),
            crop[-border_width:].reshape(-1, 3),
            crop[:, :border_width].reshape(-1, 3),
            crop[:, -border_width:].reshape(-1, 3),
        ],
        axis=0,
    )
    background = np.median(border.astype(np.float32), axis=0)
    diff = np.linalg.norm(crop.astype(np.float32) - background.reshape(1, 1, 3), axis=2)
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    value = hsv[:, :, 2]
    saturation = hsv[:, :, 1]
    mask_bool = ((diff > 18.0) | ((saturation > 28) & (value < 245))) & (value < 252)
    mask = mask_bool.astype(np.uint8) * 255
    kernel = np.ones((5, 5), dtype=np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.bitwise_and(mask, central_prior)

    if int(np.count_nonzero(mask)) > int(h * w * 0.40):
        strict = ((diff > 32.0) | ((saturation > 45) & (value < 235))) & (value < 245)
        mask = cv2.bitwise_and(strict.astype(np.uint8) * 255, central_prior)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    component_count, labels, stats, _centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if component_count > 1:
        center = np.array([w / 2.0, h / 2.0], dtype=np.float32)
        best_label = 1
        best_score = float("-inf")
        for label in range(1, component_count):
            area = float(stats[label, cv2.CC_STAT_AREA])
            if area < max(32.0, h * w * 0.002):
                continue
            cx = float(stats[label, cv2.CC_STAT_LEFT] + stats[label, cv2.CC_STAT_WIDTH] / 2.0)
            cy = float(stats[label, cv2.CC_STAT_TOP] + stats[label, cv2.CC_STAT_HEIGHT] / 2.0)
            distance = float(np.linalg.norm(np.array([cx, cy], dtype=np.float32) - center))
            score = area - distance * max(h, w) * 0.5
            if score > best_score:
                best_score = score
                best_label = label
        mask = np.where(labels == best_label, 255, 0).astype(np.uint8)

    mask_area = int(np.count_nonzero(mask))
    if mask_area < max(64, h * w // 100) or mask_area > int(h * w * 0.55):
        mask = np.zeros((h, w), dtype=np.uint8)
        cv2.ellipse(mask, (w // 2, h // 2), (max(4, w // 4), max(4, h // 4)), 0, 0, 360, 255, -1)

    mask = cv2.dilate(mask, np.ones((5, 5), dtype=np.uint8), iterations=1)
    mask = cv2.GaussianBlur(mask, (9, 9), 0)
    return mask


def _mask_bbox(mask: np.ndarray) -> tuple[int, int, int, int]:
    points = cv2.findNonZero((mask > 20).astype(np.uint8))
    if points is None:
        h, w = mask.shape[:2]
        return 0, 0, w, h
    x, y, w, h = cv2.boundingRect(points)
    return int(x), int(y), int(x + w), int(y + h)


def _crop_to_mask(crop: np.ndarray, mask: np.ndarray, padding: int = 12) -> tuple[np.ndarray, np.ndarray]:
    x1, y1, x2, y2 = _mask_bbox(mask)
    h, w = crop.shape[:2]
    x1 = max(0, x1 - padding)
    y1 = max(0, y1 - padding)
    x2 = min(w, x2 + padding)
    y2 = min(h, y2 + padding)
    return crop[y1:y2, x1:x2], mask[y1:y2, x1:x2]


def _augment_crop(crop: np.ndarray, rng: random.Random) -> np.ndarray:
    alpha = rng.uniform(0.88, 1.12)
    beta = rng.uniform(-10.0, 10.0)
    adjusted = cv2.convertScaleAbs(crop, alpha=alpha, beta=beta)
    if rng.random() < 0.35:
        adjusted = cv2.GaussianBlur(adjusted, (3, 3), 0)
    if rng.random() < 0.50:
        noise = rng.uniform(2.0, 6.0)
        gaussian = np.random.default_rng(rng.randrange(2**32)).normal(0.0, noise, adjusted.shape)
        adjusted = np.clip(adjusted.astype(np.float32) + gaussian, 0, 255).astype(np.uint8)
    return adjusted


def _resize_cell_to_anchor(
    crop: np.ndarray,
    mask: np.ndarray,
    target_size: tuple[int, int],
    rng: random.Random,
    jitter: tuple[float, float],
) -> tuple[np.ndarray, np.ndarray]:
    x1, y1, x2, y2 = _mask_bbox(mask)
    mask_w = max(1, x2 - x1)
    mask_h = max(1, y2 - y1)
    target_w, target_h = target_size
    scale = min(target_w / mask_w, target_h / mask_h) * rng.uniform(jitter[0], jitter[1])
    new_w = max(8, int(round(crop.shape[1] * scale)))
    new_h = max(8, int(round(crop.shape[0] * scale)))
    resized_crop = cv2.resize(crop, (new_w, new_h), interpolation=cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC)
    resized_mask = cv2.resize(mask, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    return resized_crop, resized_mask


def _paste_cell(
    background: np.ndarray,
    crop: np.ndarray,
    mask: np.ndarray,
    rng: random.Random,
) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    bg_h, bg_w = background.shape[:2]
    cell_h, cell_w = crop.shape[:2]
    if cell_w >= bg_w or cell_h >= bg_h:
        scale = min((bg_w * 0.75) / cell_w, (bg_h * 0.75) / cell_h)
        cell_w = max(8, int(round(cell_w * scale)))
        cell_h = max(8, int(round(cell_h * scale)))
        crop = cv2.resize(crop, (cell_w, cell_h), interpolation=cv2.INTER_AREA)
        mask = cv2.resize(mask, (cell_w, cell_h), interpolation=cv2.INTER_LINEAR)

    x = rng.randint(0, max(0, bg_w - cell_w))
    y = rng.randint(0, max(0, bg_h - cell_h))
    output = background.copy()
    roi = output[y : y + cell_h, x : x + cell_w]
    alpha = (mask.astype(np.float32) / 255.0)[:, :, None] * rng.uniform(0.78, 0.98)
    blended = roi.astype(np.float32) * (1.0 - alpha) + crop.astype(np.float32) * alpha
    output[y : y + cell_h, x : x + cell_w] = np.clip(blended, 0, 255).astype(np.uint8)
    mx1, my1, mx2, my2 = _mask_bbox(mask)
    bbox = x + mx1, y + my1, x + mx2, y + my2
    return output, bbox


def _xyxy_to_yolo(box: tuple[int, int, int, int], width: int, height: int) -> str:
    x1, y1, x2, y2 = box
    cx = ((x1 + x2) / 2.0) / width
    cy = ((y1 + y2) / 2.0) / height
    box_w = (x2 - x1) / width
    box_h = (y2 - y1) / height
    return f"0 {cx:.8f} {cy:.8f} {box_w:.8f} {box_h:.8f}"


def _write_data_yaml(output_root: Path) -> Path:
    path = output_root / "data.yaml"
    path.write_text(
        (
            f"path: {output_root.resolve().as_posix()}\n"
            "train: images/train\n"
            "val: images/val\n"
            "nc: 1\n"
            "names:\n"
            "  0: WBC\n"
        ),
        encoding="utf-8",
    )
    return path


def _reset_output(output_root: Path, overwrite: bool) -> None:
    if output_root.exists():
        if not overwrite:
            raise FileExistsError(f"Output root already exists. Pass --overwrite to replace it: {output_root}")
        shutil.rmtree(output_root)
    for split in ("train", "val"):
        (output_root / "images" / split).mkdir(parents=True, exist_ok=True)
        (output_root / "labels" / split).mkdir(parents=True, exist_ok=True)


def _copy_real_anchor_samples(
    samples: Iterable[AnchorSample],
    output_root: Path,
    split: str,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for sample in samples:
        output_name = f"real__{sample.session}__{sample.image_path.stem}{sample.image_path.suffix.lower()}"
        image_out = output_root / "images" / split / output_name
        label_out = output_root / "labels" / split / f"{Path(output_name).stem}.txt"
        shutil.copy2(sample.image_path, image_out)
        yolo_rows = [_xyxy_to_yolo(box, sample.image_width, sample.image_height) for box in sample.boxes_xyxy]
        label_out.write_text("\n".join(yolo_rows) + "\n", encoding="utf-8")
        rows.append(
            {
                "split": split,
                "kind": "real_anchor",
                "source": str(sample.image_path.resolve()),
                "source_class": "WBC",
                "image": str(image_out),
                "label": str(label_out),
                "boxes": str(len(yolo_rows)),
            }
        )
    return rows


def build_wbc400_wbc_only_dataset(
    *,
    anchor_session: Path,
    mll23_root: Path,
    output_root: Path,
    mll23_classes: Iterable[str] = DEFAULT_MLL23_CLASSES,
    synthetic_count: int = 200,
    val_ratio: float = 0.2,
    seed: int = 42,
    max_crops_per_class: int | None = 1000,
    target_width: int | None = None,
    target_height: int | None = None,
    scale_jitter: tuple[float, float] = (0.85, 1.15),
    include_real_anchor: bool = True,
    real_anchor_split: str = "val",
    overwrite: bool = False,
) -> Path:
    rng = random.Random(seed)
    anchor_samples = load_anchor_samples(anchor_session)
    anchor_width, anchor_height = anchor_target_size(anchor_samples)
    target_size = (int(target_width or anchor_width), int(target_height or anchor_height))
    crops = discover_mll23_crops(mll23_root, mll23_classes, max_per_class=max_crops_per_class)
    if synthetic_count > 0 and not crops:
        raise ValueError(f"No MLL23 WBC crop images found under: {mll23_root}")

    _reset_output(output_root, overwrite=overwrite)
    manifest_rows: list[dict[str, str]] = []
    if include_real_anchor:
        manifest_rows.extend(_copy_real_anchor_samples(anchor_samples, output_root, split=real_anchor_split))

    background_paths = [sample.image_path for sample in anchor_samples]
    for index in range(int(synthetic_count)):
        split = "val" if rng.random() < val_ratio else "train"
        background = read_image(rng.choice(background_paths))
        crop_source = rng.choice(crops)
        crop = read_image(crop_source.path)
        if rng.random() < 0.5:
            crop = cv2.flip(crop, 1)
        if rng.random() < 0.5:
            crop = cv2.flip(crop, 0)
        mask = _make_cell_mask(crop)
        crop, mask = _crop_to_mask(crop, mask)
        crop = _augment_crop(crop, rng)
        crop, mask = _resize_cell_to_anchor(crop, mask, target_size, rng, scale_jitter)
        composed, bbox = _paste_cell(background, crop, mask, rng)
        height, width = composed.shape[:2]
        if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
            continue
        stem = f"synthetic_wbc400_{index:06d}_{crop_source.class_name}"
        image_out = output_root / "images" / split / f"{stem}.jpg"
        label_out = output_root / "labels" / split / f"{stem}.txt"
        save_image(image_out, composed)
        label_out.write_text(_xyxy_to_yolo(bbox, width, height) + "\n", encoding="utf-8")
        manifest_rows.append(
            {
                "split": split,
                "kind": "synthetic",
                "source": str(crop_source.path.resolve()),
                "source_class": crop_source.class_name,
                "image": str(image_out),
                "label": str(label_out),
                "boxes": "1",
            }
        )

    data_yaml = _write_data_yaml(output_root)
    manifest_path = output_root / "wbc400_wbc_only_manifest.csv"
    with manifest_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["split", "kind", "source", "source_class", "image", "label", "boxes"])
        writer.writeheader()
        writer.writerows(manifest_rows)
    save_json(
        output_root / "dataset_summary.json",
        {
            "data_yaml": str(data_yaml),
            "anchor_session": str(anchor_session.resolve()),
            "mll23_root": str(mll23_root.resolve()),
            "mll23_classes": list(parse_class_list(mll23_classes)),
            "synthetic_count_requested": int(synthetic_count),
            "images_written": len(manifest_rows),
            "target_width": target_size[0],
            "target_height": target_size[1],
            "anchor_width": anchor_width,
            "anchor_height": anchor_height,
        },
    )
    return data_yaml


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a 400x WBC-only YOLO dataset from MLL23 WBC crops and a real 400x anchor session.")
    parser.add_argument("--anchor-session", type=Path, default=default_anchor_session())
    parser.add_argument("--mll23-root", type=Path, default=default_mll23_root())
    parser.add_argument("--output-root", type=Path, default=default_output_root())
    parser.add_argument("--mll23-classes", default=",".join(DEFAULT_MLL23_CLASSES), help="Comma-separated MLL23 classes, or `quick` / `common`.")
    parser.add_argument("--download-mll23", action="store_true", help="Download selected MLL23 class archives from Zenodo before building.")
    parser.add_argument("--download-only", action="store_true", help="Only download/extract the selected archives.")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--overwrite-downloads", action="store_true")
    parser.add_argument("--synthetic-count", type=int, default=200)
    parser.add_argument("--val-ratio", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-crops-per-class", type=int, default=1000)
    parser.add_argument("--target-width", type=int, default=None)
    parser.add_argument("--target-height", type=int, default=None)
    parser.add_argument("--scale-jitter-min", type=float, default=0.85)
    parser.add_argument("--scale-jitter-max", type=float, default=1.15)
    parser.add_argument("--no-real-anchor", action="store_true", help="Do not copy the real 400x anchor sample into the output dataset.")
    parser.add_argument("--real-anchor-split", choices=("train", "val"), default="val")
    return parser


def main() -> int:
    args = _parser().parse_args()
    classes = parse_class_list(args.mll23_classes)
    if args.download_mll23:
        archives = download_mll23_archives(
            args.mll23_root,
            classes,
            overwrite=args.overwrite_downloads,
        )
        extract_archives(archives, args.mll23_root, overwrite=args.overwrite_downloads)
        print("downloaded_archives=" + ",".join(str(path) for path in archives))
    if args.download_only:
        return 0
    data_yaml = build_wbc400_wbc_only_dataset(
        anchor_session=args.anchor_session,
        mll23_root=args.mll23_root,
        output_root=args.output_root,
        mll23_classes=classes,
        synthetic_count=args.synthetic_count,
        val_ratio=args.val_ratio,
        seed=args.seed,
        max_crops_per_class=args.max_crops_per_class,
        target_width=args.target_width,
        target_height=args.target_height,
        scale_jitter=(args.scale_jitter_min, args.scale_jitter_max),
        include_real_anchor=not args.no_real_anchor,
        real_anchor_split=args.real_anchor_split,
        overwrite=args.overwrite,
    )
    print(f"data_yaml={data_yaml}")
    print(f"manifest={data_yaml.parent / 'wbc400_wbc_only_manifest.csv'}")
    print(f"summary={data_yaml.parent / 'dataset_summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
