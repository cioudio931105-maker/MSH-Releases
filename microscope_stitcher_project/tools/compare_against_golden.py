from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from statistics import median


@dataclass(frozen=True)
class Placement:
    filename: str
    x: float
    y: float


def load_placements(path: Path) -> dict[str, Placement]:
    placements: dict[str, Placement] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            filename = Path((row.get("filename") or "").strip()).name
            if not filename:
                continue
            x_raw = row.get("aligned_full_x")
            y_raw = row.get("aligned_full_y")
            if x_raw in (None, "") or y_raw in (None, ""):
                continue
            placements[filename] = Placement(filename, float(x_raw), float(y_raw))
    return placements


def compare(golden: dict[str, Placement], candidate: dict[str, Placement]):
    common = sorted(set(golden) & set(candidate))
    if not common:
        raise ValueError("No common filenames between golden and candidate placements.")

    # Remove whole-canvas shift before scoring. Mosaic origin can move when new
    # tiles extend left/up; relative tile positions are what matter.
    shift_x = median(candidate[name].x - golden[name].x for name in common)
    shift_y = median(candidate[name].y - golden[name].y for name in common)

    rows = []
    max_error = 0.0
    sum_sq = 0.0
    for name in common:
        gx = golden[name].x
        gy = golden[name].y
        cx = candidate[name].x - shift_x
        cy = candidate[name].y - shift_y
        dx = cx - gx
        dy = cy - gy
        error = (dx * dx + dy * dy) ** 0.5
        max_error = max(max_error, error)
        sum_sq += error * error
        rows.append(
            {
                "filename": name,
                "golden_x": gx,
                "golden_y": gy,
                "candidate_x_shift_corrected": cx,
                "candidate_y_shift_corrected": cy,
                "dx": dx,
                "dy": dy,
                "error_px": error,
            }
        )

    rmse = (sum_sq / len(common)) ** 0.5
    return {
        "common_count": len(common),
        "missing_in_candidate": sorted(set(golden) - set(candidate)),
        "extra_in_candidate": sorted(set(candidate) - set(golden)),
        "canvas_shift_removed": {"x": shift_x, "y": shift_y},
        "rmse_px": rmse,
        "max_error_px": max_error,
        "rows": rows,
    }


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare a stitch placements.csv against a confirmed golden answer.")
    parser.add_argument(
        "--golden",
        default=str(Path(__file__).resolve().parents[1] / "reference" / "session_20260521_181641_759929_golden_placements.csv"),
        help="Golden placements CSV.",
    )
    parser.add_argument("--candidate", required=True, help="Candidate debug/placements.csv to evaluate.")
    parser.add_argument("--output-json", default=None, help="Optional JSON report path.")
    parser.add_argument("--output-csv", default=None, help="Optional per-tile CSV report path.")
    args = parser.parse_args()

    result = compare(load_placements(Path(args.golden)), load_placements(Path(args.candidate)))
    printable = {key: value for key, value in result.items() if key != "rows"}
    print(json.dumps(printable, ensure_ascii=False, indent=2))

    if args.output_json:
        output_json = Path(args.output_json)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.output_csv:
        write_csv(Path(args.output_csv), result["rows"])


if __name__ == "__main__":
    main()
