from __future__ import annotations

import argparse
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


@dataclass(slots=True)
class VocPreparationResult:
    output_dir: str
    images_count: int
    annotations_count: int
    labels_path: str


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Normalize a flat image/XML folder into VOC format.")
    parser.add_argument("--input-dir", required=True, help="Input directory containing images/XML or a VOC tree.")
    parser.add_argument("--output-dir", required=True, help="Output directory for the VOC dataset.")
    parser.add_argument("--labels", default=None, help="Comma-separated labels or a text file path. Defaults to XML inference.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--copy", action="store_true", help="Copy files into the VOC dataset structure.")
    mode.add_argument("--move", action="store_true", help="Move files into the VOC dataset structure.")
    return parser


def _load_requested_labels(labels_arg: str | None, input_dir: Path) -> list[str]:
    if labels_arg is None:
        labels_file = input_dir / "labels.txt"
        if labels_file.exists():
            labels_arg = str(labels_file)
    if labels_arg is None:
        return []

    candidate = Path(labels_arg)
    if candidate.exists():
        labels = candidate.read_text(encoding="utf-8").splitlines()
    else:
        labels = [item.strip() for item in labels_arg.split(",")]
    return [label for label in labels if label and label.upper() != "BACKGROUND"]


def _discover_sources(input_dir: Path) -> tuple[Path, Path]:
    image_dir = input_dir / "JPEGImages"
    annotation_dir = input_dir / "Annotations"
    if image_dir.is_dir() and annotation_dir.is_dir():
        return image_dir, annotation_dir
    return input_dir, input_dir


def _collect_pairs(image_root: Path, annotation_root: Path) -> list[tuple[Path, Path]]:
    images = {path.stem: path for path in image_root.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES}
    xmls = {path.stem: path for path in annotation_root.iterdir() if path.is_file() and path.suffix.lower() == ".xml"}
    shared = sorted(set(images) & set(xmls))
    if not shared:
        raise FileNotFoundError(f"No matching image/XML pairs were found in {image_root} and {annotation_root}.")
    return [(images[stem], xmls[stem]) for stem in shared]


def _infer_labels(xml_paths: list[Path]) -> list[str]:
    labels: set[str] = set()
    for xml_path in xml_paths:
        root = ET.parse(xml_path).getroot()
        for obj in root.findall("object"):
            name = (obj.findtext("name") or "").strip()
            if name:
                labels.add(name)
    return sorted(labels)


def _copy_or_move(src: Path, dst: Path, move_files: bool) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.resolve() == dst.resolve():
        return
    if move_files:
        shutil.move(str(src), str(dst))
    else:
        shutil.copy2(str(src), str(dst))


def prepare_voc_dataset(input_dir: str | Path, output_dir: str | Path, labels: str | None = None, move_files: bool = False) -> VocPreparationResult:
    source_root = Path(input_dir)
    target_root = Path(output_dir)
    image_root, annotation_root = _discover_sources(source_root)
    pairs = _collect_pairs(image_root=image_root, annotation_root=annotation_root)

    jpeg_dir = target_root / "JPEGImages"
    xml_dir = target_root / "Annotations"
    sets_dir = target_root / "ImageSets" / "Main"
    jpeg_dir.mkdir(parents=True, exist_ok=True)
    xml_dir.mkdir(parents=True, exist_ok=True)
    sets_dir.mkdir(parents=True, exist_ok=True)

    stems: list[str] = []
    for image_path, xml_path in pairs:
        stems.append(image_path.stem)
        _copy_or_move(image_path, jpeg_dir / image_path.name, move_files=move_files)
        _copy_or_move(xml_path, xml_dir / xml_path.name, move_files=move_files)

    label_names = _load_requested_labels(labels, source_root) or _infer_labels([xml_path for _, xml_path in pairs])
    (target_root / "labels.txt").write_text("\n".join(label_names) + "\n", encoding="utf-8")

    dataset_listing = "\n".join(stems) + "\n"
    for split_name in ("train", "val", "test", "trainval", "default"):
        (sets_dir / f"{split_name}.txt").write_text(dataset_listing, encoding="utf-8")

    return VocPreparationResult(
        output_dir=str(target_root.resolve()),
        images_count=len(stems),
        annotations_count=len(stems),
        labels_path=str((target_root / "labels.txt").resolve()),
    )


def main() -> int:
    args = _parser().parse_args()
    result = prepare_voc_dataset(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        labels=args.labels,
        move_files=bool(args.move),
    )
    print(f"output_dir={result.output_dir}")
    print(f"images_count={result.images_count}")
    print(f"annotations_count={result.annotations_count}")
    print(f"labels_path={result.labels_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
