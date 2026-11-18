from __future__ import annotations

# Direct source entrypoints also resolve shared modules from the workspace.
import sys as _msh_sys
from pathlib import Path as _MshPath
if not getattr(_msh_sys, "frozen", False):
    _msh_sys.path.insert(0, str(_MshPath(__file__).resolve().parents[2]))


import argparse
import csv
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from msh_app.core.msh_runtime import default_output_dir
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from PIL import Image, ImageTk
except Exception as exc:  # pragma: no cover - GUI dependency guard
    raise SystemExit("Pillow is required. Install with: pip install pillow") from exc

try:
    from pypylon import pylon  # type: ignore
except Exception:  # pragma: no cover - optional Basler dependency
    pylon = None  # type: ignore


CLASS_NAMES: tuple[str, ...] = ("WBC", "RBC", "Platelets")
CLASS_DIRS: dict[int, str] = {
    0: "white_blood_cell",
    1: "red_blood_cell",
    2: "platelet",
}
CLASS_COLORS: dict[int, str] = {
    0: "#00ff66",
    1: "#ffff00",
    2: "#ff3333",
}


@dataclass
class AnnotationBox:
    class_id: int
    x1: int
    y1: int
    x2: int
    y2: int

    def normalized_yolo(self, width: int, height: int) -> str:
        left = max(0, min(self.x1, self.x2))
        right = min(width - 1, max(self.x1, self.x2))
        top = max(0, min(self.y1, self.y2))
        bottom = min(height - 1, max(self.y1, self.y2))
        cx = ((left + right) / 2.0) / width
        cy = ((top + bottom) / 2.0) / height
        bw = max(1.0, right - left) / width
        bh = max(1.0, bottom - top) / height
        return f"{self.class_id} {cx:.8f} {cy:.8f} {bw:.8f} {bh:.8f}"

    def crop_bounds(self, width: int, height: int, margin_ratio: float = 0.08) -> tuple[int, int, int, int]:
        left = max(0, min(self.x1, self.x2))
        right = min(width - 1, max(self.x1, self.x2))
        top = max(0, min(self.y1, self.y2))
        bottom = min(height - 1, max(self.y1, self.y2))
        margin = int(max(right - left, bottom - top) * margin_ratio)
        return (
            max(0, left - margin),
            max(0, top - margin),
            min(width, right + margin),
            min(height, bottom + margin),
        )


class CameraSource:
    def __init__(self, camera_index: int = 0, pfs_path: Path | None = None) -> None:
        self.camera_index = camera_index
        self.pfs_path = pfs_path
        self.kind = "none"
        self._camera: Any = None
        self._converter: Any = None
        self._capture: cv2.VideoCapture | None = None

    def open(self) -> str:
        if pylon is not None:
            try:
                factory = pylon.TlFactory.GetInstance()
                devices = factory.EnumerateDevices()
                if devices:
                    self._camera = pylon.InstantCamera(factory.CreateDevice(devices[0]))
                    self._camera.Open()
                    if self.pfs_path and self.pfs_path.is_file():
                        pylon.FeaturePersistence.Load(str(self.pfs_path), self._camera.GetNodeMap(), True)
                    self._camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
                    self._converter = pylon.ImageFormatConverter()
                    self._converter.OutputPixelFormat = pylon.PixelType_BGR8packed
                    self._converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned
                    self.kind = "basler"
                    return f"Basler camera opened: {self._camera.GetDeviceInfo().GetModelName()}"
            except Exception as exc:
                self.close()
                # Fall through to OpenCV webcam; keep the UI usable on non-Basler machines.
                fallback_message = f"Basler open failed, fallback to OpenCV camera: {exc}"
            else:
                fallback_message = ""
        else:
            fallback_message = "pypylon not available, fallback to OpenCV camera."

        self._capture = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        if not self._capture.isOpened():
            self.close()
            raise RuntimeError(f"{fallback_message} OpenCV camera index {self.camera_index} failed.")
        self.kind = "opencv"
        return fallback_message or f"OpenCV camera opened: index {self.camera_index}"

    def read(self) -> np.ndarray | None:
        if self.kind == "basler" and self._camera is not None:
            if not self._camera.IsGrabbing():
                return None
            grab = self._camera.RetrieveResult(500, pylon.TimeoutHandling_Return)
            try:
                if grab and grab.GrabSucceeded():
                    converted = self._converter.Convert(grab)
                    return converted.GetArray().copy()
            finally:
                if grab:
                    grab.Release()
            return None
        if self.kind == "opencv" and self._capture is not None:
            ok, frame = self._capture.read()
            return frame if ok else None
        return None

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None
        if self._camera is not None:
            try:
                if self._camera.IsGrabbing():
                    self._camera.StopGrabbing()
                if self._camera.IsOpen():
                    self._camera.Close()
            except Exception:
                pass
            self._camera = None
        self.kind = "none"


class LiveCellAnnotator(tk.Tk):
    def __init__(self, output_root: Path, camera_index: int = 0, pfs_path: Path | None = None) -> None:
        super().__init__()
        self.title("即時血球人工標註工具")
        self.geometry("1320x900")
        self.minsize(1000, 720)

        self.output_root = output_root.resolve()
        self.camera = CameraSource(camera_index=camera_index, pfs_path=pfs_path)
        self.live_frame: np.ndarray | None = None
        self.frozen_frame: np.ndarray | None = None
        self.annotations: list[AnnotationBox] = []
        self.class_var = tk.IntVar(value=0)
        self.status_var = tk.StringVar(value="尚未開啟相機")
        self.output_var = tk.StringVar(value=str(self.output_root))
        self.pfs_var = tk.StringVar(value=str(pfs_path) if pfs_path else "")
        self.freeze_var = tk.BooleanVar(value=False)

        self._display_image: ImageTk.PhotoImage | None = None
        self._scale = 1.0
        self._offset_x = 0
        self._offset_y = 0
        self._drag_start: tuple[int, int] | None = None
        self._preview_item: int | None = None
        self._running = False

        self._build_ui()
        self._bind_keys()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        top = ttk.Frame(self)
        top.pack(side=tk.TOP, fill=tk.X, padx=8, pady=6)

        ttk.Button(top, text="開啟相機", command=self.open_camera).pack(side=tk.LEFT, padx=3)
        ttk.Button(top, text="凍結目前畫面", command=self.freeze_current_frame).pack(side=tk.LEFT, padx=3)
        ttk.Button(top, text="恢復即時", command=self.resume_live).pack(side=tk.LEFT, padx=3)
        ttk.Button(top, text="儲存標註資料", command=self.save_annotation).pack(side=tk.LEFT, padx=3)
        ttk.Button(top, text="Undo", command=self.undo_box).pack(side=tk.LEFT, padx=3)
        ttk.Button(top, text="清除框", command=self.clear_boxes).pack(side=tk.LEFT, padx=3)

        class_frame = ttk.LabelFrame(top, text="類別")
        class_frame.pack(side=tk.LEFT, padx=10)
        for class_id, name in enumerate(CLASS_NAMES):
            ttk.Radiobutton(
                class_frame,
                text=f"{class_id + 1}. {name}",
                variable=self.class_var,
                value=class_id,
            ).pack(side=tk.LEFT, padx=3)

        path_frame = ttk.Frame(self)
        path_frame.pack(side=tk.TOP, fill=tk.X, padx=8, pady=2)
        ttk.Label(path_frame, text="輸出資料夾").pack(side=tk.LEFT)
        ttk.Entry(path_frame, textvariable=self.output_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Button(path_frame, text="選擇", command=self.choose_output_root).pack(side=tk.LEFT, padx=3)

        pfs_frame = ttk.Frame(self)
        pfs_frame.pack(side=tk.TOP, fill=tk.X, padx=8, pady=2)
        ttk.Label(pfs_frame, text="Basler PFS").pack(side=tk.LEFT)
        ttk.Entry(pfs_frame, textvariable=self.pfs_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Button(pfs_frame, text="選擇", command=self.choose_pfs).pack(side=tk.LEFT, padx=3)

        self.canvas = tk.Canvas(self, bg="black", highlightthickness=0)
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=6)
        self.canvas.bind("<ButtonPress-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)
        self.canvas.bind("<Configure>", lambda _event: self.render())

        bottom = ttk.Frame(self)
        bottom.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=4)
        ttk.Label(bottom, textvariable=self.status_var).pack(side=tk.LEFT)
        ttk.Label(
            bottom,
            text="快捷鍵：1=WBC, 2=RBC, 3=Platelets, Space=凍結/恢復, Ctrl+S=儲存, Z=Undo",
        ).pack(side=tk.RIGHT)

    def _bind_keys(self) -> None:
        self.bind("1", lambda _event: self.class_var.set(0))
        self.bind("2", lambda _event: self.class_var.set(1))
        self.bind("3", lambda _event: self.class_var.set(2))
        self.bind("<space>", lambda _event: self.resume_live() if self.freeze_var.get() else self.freeze_current_frame())
        self.bind("<Control-s>", lambda _event: self.save_annotation())
        self.bind("z", lambda _event: self.undo_box())
        self.bind("Z", lambda _event: self.undo_box())

    def choose_output_root(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.output_var.get() or str(self.output_root))
        if selected:
            self.output_var.set(selected)
            self.output_root = Path(selected).resolve()

    def choose_pfs(self) -> None:
        selected = filedialog.askopenfilename(
            title="選擇 Basler PFS",
            filetypes=[("Basler feature stream", "*.pfs"), ("All files", "*.*")],
        )
        if selected:
            self.pfs_var.set(selected)

    def open_camera(self) -> None:
        try:
            self.camera.close()
            pfs_path = Path(self.pfs_var.get()) if self.pfs_var.get().strip() else None
            self.camera = CameraSource(camera_index=self.camera.camera_index, pfs_path=pfs_path)
            message = self.camera.open()
            self.status_var.set(message)
            self._running = True
            self.after(10, self._update_loop)
        except Exception as exc:
            messagebox.showerror("相機開啟失敗", str(exc))
            self.status_var.set(f"相機開啟失敗：{exc}")

    def _update_loop(self) -> None:
        if not self._running:
            return
        if not self.freeze_var.get():
            frame = self.camera.read()
            if frame is not None:
                self.live_frame = frame
                self.render()
        self.after(30, self._update_loop)

    def _current_frame(self) -> np.ndarray | None:
        return self.frozen_frame if self.freeze_var.get() else self.live_frame

    def freeze_current_frame(self) -> None:
        if self.live_frame is None:
            messagebox.showwarning("沒有畫面", "目前沒有可凍結的相機畫面。")
            return
        self.frozen_frame = self.live_frame.copy()
        self.freeze_var.set(True)
        self.annotations.clear()
        self.status_var.set("已凍結目前畫面，請用滑鼠框選血球。")
        self.render()

    def resume_live(self) -> None:
        self.freeze_var.set(False)
        self.frozen_frame = None
        self.annotations.clear()
        self.status_var.set("已恢復即時畫面。")
        self.render()

    def render(self) -> None:
        frame = self._current_frame()
        self.canvas.delete("all")
        self._preview_item = None
        if frame is None:
            return
        canvas_w = max(1, self.canvas.winfo_width())
        canvas_h = max(1, self.canvas.winfo_height())
        h, w = frame.shape[:2]
        self._scale = min(canvas_w / w, canvas_h / h)
        display_w = max(1, int(w * self._scale))
        display_h = max(1, int(h * self._scale))
        self._offset_x = (canvas_w - display_w) // 2
        self._offset_y = (canvas_h - display_h) // 2

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.BICUBIC)
        pil_image = Image.fromarray(rgb).resize((display_w, display_h), resample)
        self._display_image = ImageTk.PhotoImage(pil_image)
        self.canvas.create_image(self._offset_x, self._offset_y, anchor=tk.NW, image=self._display_image)
        for box in self.annotations:
            self._draw_box(box)

    def _image_xy_from_canvas(self, event_x: int, event_y: int) -> tuple[int, int] | None:
        frame = self._current_frame()
        if frame is None:
            return None
        h, w = frame.shape[:2]
        x = int((event_x - self._offset_x) / self._scale)
        y = int((event_y - self._offset_y) / self._scale)
        if x < 0 or y < 0 or x >= w or y >= h:
            return None
        return x, y

    def _canvas_xy_from_image(self, x: int, y: int) -> tuple[int, int]:
        return int(self._offset_x + x * self._scale), int(self._offset_y + y * self._scale)

    def _draw_box(self, box: AnnotationBox, temporary: bool = False) -> int:
        x1, y1 = self._canvas_xy_from_image(box.x1, box.y1)
        x2, y2 = self._canvas_xy_from_image(box.x2, box.y2)
        color = CLASS_COLORS.get(box.class_id, "#ffffff")
        options: dict[str, Any] = {"outline": color, "width": 2}
        if temporary:
            options["dash"] = (4, 3)
        item = self.canvas.create_rectangle(x1, y1, x2, y2, **options)
        label = CLASS_NAMES[box.class_id]
        self.canvas.create_text(x1 + 4, y1 + 4, anchor=tk.NW, text=label, fill=color, font=("Arial", 12, "bold"))
        return item

    def _on_mouse_down(self, event: tk.Event) -> None:
        if not self.freeze_var.get():
            self.freeze_current_frame()
        pos = self._image_xy_from_canvas(int(event.x), int(event.y))
        if pos is None:
            return
        self._drag_start = pos

    def _on_mouse_drag(self, event: tk.Event) -> None:
        if self._drag_start is None:
            return
        pos = self._image_xy_from_canvas(int(event.x), int(event.y))
        if pos is None:
            return
        self.render()
        preview = AnnotationBox(self.class_var.get(), self._drag_start[0], self._drag_start[1], pos[0], pos[1])
        self._preview_item = self._draw_box(preview, temporary=True)

    def _on_mouse_up(self, event: tk.Event) -> None:
        if self._drag_start is None:
            return
        pos = self._image_xy_from_canvas(int(event.x), int(event.y))
        start = self._drag_start
        self._drag_start = None
        if pos is None:
            self.render()
            return
        if abs(pos[0] - start[0]) < 6 or abs(pos[1] - start[1]) < 6:
            self.render()
            return
        self.annotations.append(AnnotationBox(self.class_var.get(), start[0], start[1], pos[0], pos[1]))
        self.status_var.set(f"目前標註框數：{len(self.annotations)}")
        self.render()

    def undo_box(self) -> None:
        if self.annotations:
            self.annotations.pop()
            self.status_var.set(f"已復原，剩餘標註框數：{len(self.annotations)}")
            self.render()

    def clear_boxes(self) -> None:
        self.annotations.clear()
        self.status_var.set("已清除所有標註框。")
        self.render()

    def _ensure_dataset_dirs(self) -> dict[str, Path]:
        dataset = self.output_root / "manual_annotation_dataset"
        paths = {
            "dataset": dataset,
            "images": dataset / "images" / "train",
            "labels": dataset / "labels" / "train",
            "crops": dataset / "crops",
        }
        for path in paths.values():
            path.mkdir(parents=True, exist_ok=True)
        for class_dir in CLASS_DIRS.values():
            (paths["crops"] / class_dir).mkdir(parents=True, exist_ok=True)
        data_yaml = dataset / "data.yaml"
        if not data_yaml.exists():
            names_text = "\n".join(f"  {index}: {name}" for index, name in enumerate(CLASS_NAMES))
            data_yaml.write_text(
                (
                    f"path: {dataset.resolve().as_posix()}\n"
                    "train: images/train\n"
                    "val: images/train\n"
                    "names:\n"
                    f"{names_text}\n"
                ),
                encoding="utf-8",
            )
        return paths

    def save_annotation(self) -> None:
        frame = self._current_frame()
        if frame is None:
            messagebox.showwarning("沒有畫面", "目前沒有可儲存的畫面。")
            return
        if not self.annotations:
            if not messagebox.askyesno("沒有標註框", "目前沒有任何標註框，仍要儲存影像與空 label 嗎？"):
                return
        try:
            self.output_root = Path(self.output_var.get()).resolve()
            paths = self._ensure_dataset_dirs()
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            image_name = f"manual_annotated_{stamp}.png"
            image_path = paths["images"] / image_name
            label_path = paths["labels"] / f"{Path(image_name).stem}.txt"
            cv2.imwrite(str(image_path), frame, [cv2.IMWRITE_PNG_COMPRESSION, 1])
            h, w = frame.shape[:2]
            label_path.write_text(
                "\n".join(box.normalized_yolo(w, h) for box in self.annotations) + ("\n" if self.annotations else ""),
                encoding="utf-8",
            )
            manifest_path = paths["dataset"] / "manual_annotation_manifest.csv"
            is_new = not manifest_path.exists()
            with manifest_path.open("a", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["image_path", "label_path", "class_name", "class_id", "x1", "y1", "x2", "y2", "crop_path", "created_at"],
                )
                if is_new:
                    writer.writeheader()
                for index, box in enumerate(self.annotations, start=1):
                    left, top, right, bottom = box.crop_bounds(w, h)
                    class_dir = CLASS_DIRS[box.class_id]
                    crop_path = paths["crops"] / class_dir / f"{Path(image_name).stem}_{class_dir}_{index:04d}.png"
                    cv2.imwrite(str(crop_path), frame[top:bottom, left:right], [cv2.IMWRITE_PNG_COMPRESSION, 1])
                    writer.writerow(
                        {
                            "image_path": str(image_path),
                            "label_path": str(label_path),
                            "class_name": CLASS_NAMES[box.class_id],
                            "class_id": box.class_id,
                            "x1": min(box.x1, box.x2),
                            "y1": min(box.y1, box.y2),
                            "x2": max(box.x1, box.x2),
                            "y2": max(box.y1, box.y2),
                            "crop_path": str(crop_path),
                            "created_at": datetime.now().isoformat(timespec="seconds"),
                        }
                    )
            self.status_var.set(f"已儲存：{image_path}，標註框={len(self.annotations)}")
            self.annotations.clear()
            self.resume_live()
        except Exception as exc:
            messagebox.showerror("儲存失敗", str(exc))
            self.status_var.set(f"儲存失敗：{exc}")

    def _on_close(self) -> None:
        self._running = False
        self.camera.close()
        time.sleep(0.05)
        self.destroy()


def default_output_root() -> Path:
    return default_output_dir("annotator")


def default_pfs_path() -> Path | None:
    """Require an explicit user-selected PFS profile for the active camera."""
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Live camera annotation window for WBC/RBC/Platelets YOLO datasets.")
    parser.add_argument("--output-root", type=Path, default=default_output_root())
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--pfs", type=Path, default=default_pfs_path())
    parser.add_argument("--no-pfs", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pfs_path = None if args.no_pfs else args.pfs
    app = LiveCellAnnotator(output_root=args.output_root, camera_index=args.camera_index, pfs_path=pfs_path)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
