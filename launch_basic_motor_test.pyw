"""Launch the isolated motor test without loading the original MSH GUI."""

from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    try:
        from msh_app.hardware.basic_motor_gui import main
        main()
    except Exception:
        import tkinter as tk
        from tkinter import messagebox
        error_root = tk.Tk()
        error_root.withdraw()
        messagebox.showerror("MSH 雙馬達測試啟動失敗", traceback.format_exc(), parent=error_root)
        error_root.destroy()
