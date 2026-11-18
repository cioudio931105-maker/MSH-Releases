from __future__ import annotations

import queue
import subprocess
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


def _application_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


PROJECT_DIR = _application_dir()
WORKSPACE_ROOT = PROJECT_DIR.parent
_PYTHON_EXECUTABLE_CACHE: str | None = None
DEFAULT_MODEL = (
    WORKSPACE_ROOT
    / "stitched_output"
    / "stitched_output"
    / "stitched_output"
    / "models"
    / "blood_cells_3cls_yolov8n_20260429.pt"
)


def _find_default_cell_model() -> Path | None:
    candidates = [
        DEFAULT_MODEL,
        WORKSPACE_ROOT
        / "stitched_output"
        / "stitched_output"
        / "stitched_output"
        / "models"
        / "blood_cells_3cls_400x_refine_20260517.pt",
        WORKSPACE_ROOT
        / "staging"
        / "train"
        / "blood_cells_3cls_400x_refine_gpu_20260517"
        / "weights"
        / "best.pt",
        WORKSPACE_ROOT
        / "staging"
        / "train"
        / "blood_cells_3cls_yolov8n_20260517"
        / "weights"
        / "best.pt",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


class OfflineAnalysisGUI:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("離線細胞影片分析")
        self.root.geometry("980x680")

        default_model = _find_default_cell_model()
        self.video_var = tk.StringVar(value="")
        self.model_var = tk.StringVar(value=str(default_model if default_model else PROJECT_DIR / "models"))
        self.every_n_frames_var = tk.IntVar(value=5)
        self.every_seconds_var = tk.StringVar(value="")
        self.blur_threshold_var = tk.DoubleVar(value=80.0)
        self.conf_var = tk.DoubleVar(value=0.25)
        self.device_var = tk.StringVar(value="auto")
        self.batch_size_var = tk.IntVar(value=8)
        self.save_annotated_var = tk.BooleanVar(value=True)
        self.single_cell_crops_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="狀態：待命")

        self.process: subprocess.Popen[str] | None = None
        self.output_queue: queue.Queue[object] = queue.Queue()

        self._build_ui()
        self.root.after(100, self._drain_output_queue)
        self.root.after(250, self._detect_default_device_async)

    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)
        main.columnconfigure(1, weight=1)

        ttk.Label(main, text="影片檔案").grid(row=0, column=0, sticky=tk.W, pady=4)
        ttk.Entry(main, textvariable=self.video_var).grid(row=0, column=1, sticky=tk.EW, padx=8, pady=4)
        ttk.Button(main, text="選擇影片", command=self._choose_video).grid(row=0, column=2, pady=4)

        ttk.Label(main, text="YOLO 模型").grid(row=1, column=0, sticky=tk.W, pady=4)
        ttk.Entry(main, textvariable=self.model_var).grid(row=1, column=1, sticky=tk.EW, padx=8, pady=4)
        model_buttons = ttk.Frame(main)
        model_buttons.grid(row=1, column=2, sticky=tk.W, pady=4)
        ttk.Button(model_buttons, text="選擇模型", command=self._choose_model).pack(side=tk.LEFT)
        ttk.Button(model_buttons, text="使用預設模型", command=self._use_default_model).pack(side=tk.LEFT, padx=(6, 0))

        settings = ttk.LabelFrame(main, text="分析設定")
        settings.grid(row=2, column=0, columnspan=3, sticky=tk.EW, pady=(8, 8))
        for col in range(8):
            settings.columnconfigure(col, weight=1 if col in (1, 3, 5, 7) else 0)

        ttk.Label(settings, text="每 N 幀抽 1 張").grid(row=0, column=0, sticky=tk.W, padx=6, pady=6)
        ttk.Entry(settings, textvariable=self.every_n_frames_var, width=10).grid(row=0, column=1, sticky=tk.W, padx=6, pady=6)

        ttk.Label(settings, text="每幾秒抽 1 張").grid(row=0, column=2, sticky=tk.W, padx=6, pady=6)
        ttk.Entry(settings, textvariable=self.every_seconds_var, width=10).grid(row=0, column=3, sticky=tk.W, padx=6, pady=6)

        ttk.Label(settings, text="模糊門檻").grid(row=0, column=4, sticky=tk.W, padx=6, pady=6)
        ttk.Entry(settings, textvariable=self.blur_threshold_var, width=10).grid(row=0, column=5, sticky=tk.W, padx=6, pady=6)

        ttk.Label(settings, text="信心值門檻").grid(row=1, column=0, sticky=tk.W, padx=6, pady=6)
        ttk.Entry(settings, textvariable=self.conf_var, width=10).grid(row=1, column=1, sticky=tk.W, padx=6, pady=6)

        ttk.Label(settings, text="運算裝置").grid(row=1, column=2, sticky=tk.W, padx=6, pady=6)
        ttk.Combobox(settings, textvariable=self.device_var, values=("cpu", "cuda", "0", "auto"), width=8).grid(
            row=1, column=3, sticky=tk.W, padx=6, pady=6
        )

        ttk.Label(settings, text="批次大小").grid(row=1, column=4, sticky=tk.W, padx=6, pady=6)
        ttk.Entry(settings, textvariable=self.batch_size_var, width=10).grid(row=1, column=5, sticky=tk.W, padx=6, pady=6)

        ttk.Checkbutton(settings, text="儲存標註後影格", variable=self.save_annotated_var).grid(
            row=1, column=6, columnspan=2, sticky=tk.W, padx=6, pady=6
        )
        ttk.Checkbutton(settings, text="單顆細胞裁切分類", variable=self.single_cell_crops_var).grid(
            row=2, column=0, columnspan=3, sticky=tk.W, padx=6, pady=6
        )

        actions = ttk.Frame(main)
        actions.grid(row=3, column=0, columnspan=3, sticky=tk.EW, pady=(0, 8))
        ttk.Button(actions, text="開始分析", command=self._start_analysis).pack(side=tk.LEFT)
        ttk.Button(actions, text="停止", command=self._stop_analysis).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(actions, text="開啟輸出資料夾", command=self._open_outputs).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(actions, text="開啟細胞裁切圖", command=self._open_cropped_cells).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(actions, textvariable=self.status_var).pack(side=tk.LEFT, padx=(16, 0))

        log_frame = ttk.LabelFrame(main, text="執行紀錄")
        log_frame.grid(row=4, column=0, columnspan=3, sticky=tk.NSEW)
        main.rowconfigure(4, weight=1)
        self.log_text = tk.Text(log_frame, wrap=tk.NONE, height=20)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        yscroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        yscroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=yscroll.set)

    def _choose_video(self) -> None:
        path = filedialog.askopenfilename(
            initialdir=str(PROJECT_DIR / "videos"),
            filetypes=[("影片檔", "*.mp4 *.avi *.mov *.mkv"), ("所有檔案", "*.*")],
        )
        if path:
            self.video_var.set(path)

    def _choose_model(self) -> None:
        initial_model = _find_default_cell_model()
        path = filedialog.askopenfilename(
            initialdir=str(initial_model.parent if initial_model else PROJECT_DIR / "models"),
            filetypes=[("YOLO 模型", "*.pt"), ("所有檔案", "*.*")],
        )
        if path:
            self.model_var.set(path)

    def _use_default_model(self) -> None:
        model = _find_default_cell_model()
        if model is None:
            messagebox.showwarning(
                "找不到預設模型",
                "目前專案內找不到 RBC/WBC/Platelet 的 3 分類 YOLO 模型，請手動選擇 .pt 模型。",
            )
            return
        self.model_var.set(str(model))
        self._append_log(f"已套用預設細胞模型：{model}")

    def _append_log(self, text: str) -> None:
        self.log_text.insert(tk.END, text)
        if not text.endswith("\n"):
            self.log_text.insert(tk.END, "\n")
        self.log_text.see(tk.END)

    def _build_command(self) -> list[str]:
        video = Path(self.video_var.get().strip())
        model = Path(self.model_var.get().strip())
        if not video.exists():
            raise FileNotFoundError(f"找不到影片檔案：{video}")
        if not model.exists():
            raise FileNotFoundError(f"找不到 YOLO 模型：{model}")

        cmd = [
            self._python_executable(),
            str(PROJECT_DIR / "main.py"),
            "--video",
            str(video),
            "--model",
            str(model),
            "--every-n-frames",
            str(max(1, int(self.every_n_frames_var.get()))),
            "--blur-threshold",
            str(float(self.blur_threshold_var.get())),
            "--conf",
            str(float(self.conf_var.get())),
            "--device",
            self.device_var.get().strip() or "auto",
            "--batch-size",
            str(max(1, int(self.batch_size_var.get()))),
        ]

        every_seconds = self.every_seconds_var.get().strip()
        if every_seconds:
            cmd.extend(["--every-seconds", every_seconds])
        if self.save_annotated_var.get():
            cmd.append("--save-annotated")
        if self.single_cell_crops_var.get():
            cmd.append("--single-cell-crops")
        return cmd

    def _detect_default_device_async(self) -> None:
        def worker() -> None:
            device = "cpu"
            try:
                result = subprocess.run(
                    [
                        self._python_executable(),
                        "-c",
                        "import torch; print('cuda' if torch.cuda.is_available() else 'cpu')",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=8,
                    creationflags=self._subprocess_creationflags(),
                )
                value = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
                if result.returncode == 0 and value in {"cuda", "cpu"}:
                    device = value
            except Exception:
                device = "cpu"
            self.output_queue.put(("__DEVICE__", device))

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def _python_executable() -> str:
        global _PYTHON_EXECUTABLE_CACHE
        if _PYTHON_EXECUTABLE_CACHE:
            return _PYTHON_EXECUTABLE_CACHE

        if not getattr(sys, "frozen", False):
            _PYTHON_EXECUTABLE_CACHE = sys.executable
            return _PYTHON_EXECUTABLE_CACHE

        candidates = [
            PROJECT_DIR.parent / ".venv312" / "Scripts" / "python.exe",
            PROJECT_DIR.parent / ".venv" / "Scripts" / "python.exe",
            Path("python"),
            Path("py"),
        ]
        if not getattr(sys, "frozen", False):
            candidates.insert(0, Path(sys.executable))
        for candidate in candidates:
            if candidate.name not in {"python", "py"} and not candidate.exists():
                continue
            candidate_text = str(candidate)
            try:
                result = subprocess.run(
                    [candidate_text, "-c", "import sys; print(sys.executable)"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=8,
                    creationflags=OfflineAnalysisGUI._subprocess_creationflags(),
                )
            except Exception:
                continue
            if result.returncode == 0:
                _PYTHON_EXECUTABLE_CACHE = candidate_text
                return _PYTHON_EXECUTABLE_CACHE
        raise RuntimeError("找不到可用的 Python。請確認命令列執行 python 可以正常啟動。")

    @staticmethod
    def _subprocess_creationflags() -> int:
        if sys.platform.startswith("win"):
            return getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return 0

    def _start_analysis(self) -> None:
        if self.process is not None and self.process.poll() is None:
            messagebox.showwarning("離線分析", "分析已在執行中。")
            return
        try:
            cmd = self._build_command()
        except Exception as exc:
            messagebox.showerror("設定錯誤", str(exc))
            return

        self.log_text.delete("1.0", tk.END)
        self._append_log("執行命令：")
        self._append_log(" ".join(f'"{part}"' if " " in part else part for part in cmd))
        self._append_log("")
        self.status_var.set("狀態：分析中")

        def worker() -> None:
            try:
                self.process = subprocess.Popen(
                    cmd,
                    cwd=str(PROJECT_DIR),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=self._subprocess_creationflags(),
                )
                assert self.process.stdout is not None
                for line in self.process.stdout:
                    self.output_queue.put(line)
                code = self.process.wait()
                if code == 0:
                    self.output_queue.put("\nProcess exited with code 0\n")
                    self.output_queue.put("__DONE__")
                else:
                    self.output_queue.put(f"\nProcess exited with code {code}\n")
                    self.output_queue.put(
                        "分析失敗。請查看上方錯誤訊息。常見原因：模型選錯、影片無法讀取，"
                        "或在 CPU 版 Python 環境中選擇了 CUDA。\n"
                    )
                    self.output_queue.put("__FAILED__")
            except Exception as exc:
                self.output_queue.put(f"\n執行失敗：{exc}\n")
                self.output_queue.put("__FAILED__")

        threading.Thread(target=worker, daemon=True).start()

    def _stop_analysis(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            self.status_var.set("狀態：停止中")

    def _open_outputs(self) -> None:
        outputs = PROJECT_DIR / "outputs"
        outputs.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["explorer", str(outputs)])

    def _open_cropped_cells(self) -> None:
        crops = PROJECT_DIR / "cropped_cells_single"
        crops.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["explorer", str(crops)])

    def _drain_output_queue(self) -> None:
        try:
            while True:
                item = self.output_queue.get_nowait()
                if isinstance(item, tuple) and item[0] == "__DEVICE__":
                    if self.process is None or self.process.poll() is not None:
                        self.device_var.set(item[1])
                        self.status_var.set(f"狀態：待命，運算裝置 {item[1]}")
                elif item == "__DONE__":
                    self.status_var.set("狀態：完成")
                    self.process = None
                elif item == "__FAILED__":
                    self.status_var.set("狀態：失敗")
                    self.process = None
                else:
                    self._append_log(item)
        except queue.Empty:
            pass
        self.root.after(100, self._drain_output_queue)

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    OfflineAnalysisGUI().run()


if __name__ == "__main__":
    main()
