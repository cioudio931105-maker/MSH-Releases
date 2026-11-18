from __future__ import annotations

import atexit
import logging
import os
import runpy
import sys
import threading
import time
import traceback
import math
import webbrowser
from pathlib import Path

import tkinter as tk
from tkinter import messagebox

from msh_runtime import (
    SingleInstanceLock,
    application_root,
    configure_logging,
    configure_runtime_environment,
    default_output_dir,
    log_unhandled_exception,
)
from msh_version import __version__
from msh_update import UpdateCheckError, UpdateManifest, check_for_update

PROJECT_ROOT = application_root()
GUI_SCRIPT = PROJECT_ROOT / "msh_app" / "hardware" / "stepper_drag_gui.py"
SPLASH_IMAGE = PROJECT_ROOT / "assets" / "msh-cyberpunk-splash-640.png"
SOURCE_STARTUP_LOG = PROJECT_ROOT / "logs" / "hardware_gui_startup.log"


def _format_update_message(manifest: UpdateManifest) -> str:
    return (
        f"目前版本：v{__version__}\n"
        f"最新版本：v{manifest.version}\n"
        f"發布日期：{manifest.published_at}\n\n"
        f"{manifest.release_name}\n\n"
        f"{manifest.release_notes}\n\n"
        f"SHA-256：\n{manifest.sha256}\n\n"
        "是否開啟瀏覽器下載新版安裝檔？\n"
        "下載後可直接覆蓋安裝，不必先解除安裝舊版。"
    )


def _install_help_menu(root: tk.Tk) -> None:
    logger = logging.getLogger("msh.update")
    state = {"checking": False}

    def finish_check(manual: bool, manifest: UpdateManifest | None, error: Exception | None) -> None:
        state["checking"] = False
        if error is not None:
            logger.warning("Update check failed: %s", error)
            if manual:
                messagebox.showwarning("MSH 檢查更新", f"目前無法取得更新資訊。\n\n{error}", parent=root)
            return
        if manifest is None:
            if manual:
                messagebox.showinfo(
                    "MSH 檢查更新",
                    f"目前已是最新版本：v{__version__}",
                    parent=root,
                )
            return
        logger.info("MSH update available: %s -> %s", __version__, manifest.version)
        if messagebox.askyesno("MSH 有可用更新", _format_update_message(manifest), parent=root):
            if not webbrowser.open(manifest.download_url, new=2):
                messagebox.showwarning(
                    "MSH 下載更新",
                    f"無法自動開啟瀏覽器，請前往：\n{manifest.release_page_url}",
                    parent=root,
                )

    def start_check(manual: bool = True) -> None:
        if state["checking"]:
            if manual:
                messagebox.showinfo("MSH 檢查更新", "正在檢查更新，請稍候。", parent=root)
            return
        state["checking"] = True

        def worker() -> None:
            manifest: UpdateManifest | None = None
            error: Exception | None = None
            try:
                manifest = check_for_update(__version__)
            except UpdateCheckError as exc:
                error = exc
            try:
                root.after(0, finish_check, manual, manifest, error)
            except tk.TclError:
                logger.info("MSH closed before the update check completed")

        threading.Thread(target=worker, name="msh-update-check", daemon=True).start()

    menu_bar = tk.Menu(root)
    help_menu = tk.Menu(menu_bar, tearoff=False)
    help_menu.add_command(label="檢查更新...", command=start_check)
    help_menu.add_separator()
    help_menu.add_command(
        label="關於 MSH",
        command=lambda: messagebox.showinfo(
            "關於 MSH",
            f"Microscope Scanner Helper\n版本 v{__version__}",
            parent=root,
        ),
    )
    menu_bar.add_cascade(label="說明", menu=help_menu)
    root.configure(menu=menu_bar)
    root.after(3000, lambda: start_check(manual=False))


def _center_window(window: tk.Tk, width: int, height: int) -> None:
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    x = max(0, (screen_width - width) // 2)
    y = max(0, (screen_height - height) // 2)
    window.geometry(f"{width}x{height}+{x}+{y}")


def _load_gui_module(result: dict[str, object], completed: threading.Event) -> None:
    try:
        if not GUI_SCRIPT.is_file():
            raise FileNotFoundError(f"Missing MSH GUI script: {GUI_SCRIPT}")
        sys.path.insert(0, str(GUI_SCRIPT.parent))
        result["module"] = runpy.run_path(str(GUI_SCRIPT), run_name="msh_gui_runtime")
    except Exception:
        result["error"] = traceback.format_exc()
    finally:
        completed.set()


def _build_splash() -> tuple[tk.Tk, tk.Canvas]:
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.configure(bg="#071627")
    _center_window(root, 640, 360)
    canvas = tk.Canvas(root, width=640, height=360, highlightthickness=0, bg="#071627")
    canvas.pack(fill=tk.BOTH, expand=True)
    if SPLASH_IMAGE.is_file():
        root._splash_image = tk.PhotoImage(file=str(SPLASH_IMAGE))  # type: ignore[attr-defined]
        canvas.create_image(0, 0, anchor=tk.NW, image=root._splash_image)
    canvas.create_rectangle(1, 1, 639, 359, outline="#1be8ff", width=2)
    return root, canvas


def _show_already_running() -> None:
    notice_root = tk.Tk()
    notice_root.withdraw()
    try:
        messagebox.showinfo("MSH", "MSH 已在執行。", parent=notice_root)
    finally:
        notice_root.destroy()


def main() -> None:
    startup_log_path = None if getattr(sys, "frozen", False) else SOURCE_STARTUP_LOG
    diagnostics = "--diagnostics" in sys.argv[1:]
    log_path = configure_logging(startup_log_path=startup_log_path, console=diagnostics)
    configure_runtime_environment()
    sys.excepthook = log_unhandled_exception
    threading.excepthook = lambda args: log_unhandled_exception(args.exc_type, args.exc_value, args.exc_traceback)
    instance_lock = SingleInstanceLock()
    if not instance_lock.acquire():
        logging.getLogger("msh.launcher").info("MSH launch skipped because another instance is running")
        _show_already_running()
        return
    atexit.register(instance_lock.close)
    if getattr(sys, "frozen", False):
        os.chdir(default_output_dir("runtime"))
    logging.getLogger("msh.launcher").info("Starting MSH %s", __version__)
    root, canvas = _build_splash()
    result: dict[str, object] = {}
    completed = threading.Event()
    threading.Thread(target=_load_gui_module, args=(result, completed), daemon=True).start()
    started = time.monotonic()

    def show_gui() -> None:
        error = result.get("error")
        if error:
            root.destroy()
            logging.getLogger("msh.launcher").error("GUI startup failed:\n%s", error)
            messagebox.showerror("MSH", f"MSH 無法啟動。\n\n詳細診斷已寫入：\n{log_path}")
            return
        module = result["module"]
        gui_class = module["StepperDragGUI"]  # type: ignore[index]
        # Keep Tk hidden while the dashboard's many widgets are constructed.
        # Otherwise destroying the splash briefly exposes Tk's white default
        # background before the GUI has painted its own content.
        root.withdraw()
        for child in root.winfo_children():
            child.destroy()
        root.overrideredirect(False)
        root.attributes("-topmost", False)
        gui_class(root=root)
        _install_help_menu(root)
        root.update_idletasks()
        root.attributes("-alpha", 1.0)
        root.deiconify()

    def animate() -> None:
        elapsed = time.monotonic() - started
        scan_x = 320
        canvas.delete("animated")
        # The wordmark itself provides the light; only loose pixel fragments move.
        for index in range(16):
            travel = (elapsed * 5 + index * 0.73) % 1.0
            x = scan_x + int(math.sin(index * 7.1) * 30 * travel)
            y = 145 + int(travel * 138)
            size = 2 + (index % 3)
            color = "#38dfff" if index % 2 == 0 else "#a75cff"
            canvas.create_rectangle(x, y, x + size, y + size, fill=color, outline="", tags="animated")
        if completed.is_set():
            root.after(120, show_gui)
            return
        root.after(33, animate)

    root.after(0, animate)
    root.mainloop()
    instance_lock.close()


if __name__ == "__main__":
    from msh_workers import dispatch_worker
    if not dispatch_worker(sys.argv[1:]):
        main()
