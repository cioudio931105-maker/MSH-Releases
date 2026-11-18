"""Conservative update gate that never stops or reconnects any device."""
from __future__ import annotations

from typing import Any


def update_blockers(gui: Any) -> list[str]:
    blockers: list[str] = []
    if any(value is not None for value in getattr(gui, "stepper_by_axis", {}).values()):
        blockers.append("請先正常停止並斷開 X/Y 馬達連線")
    if getattr(gui, "cap", None) is not None:
        blockers.append("請先停止相機預覽與取像")
    for name, value in vars(gui).items():
        if name.endswith("_running") and value:
            blockers.append("仍有拍攝、掃描、預覽或背景工作執行中")
        if name.endswith("_thread") and value is not None and value.is_alive():
            blockers.append("仍有背景執行緒尚未結束")
        if name.endswith("_process") and value is not None and value.poll() is None:
            blockers.append("仍有拼接或其他子程序尚未結束")
    if any(value is not None for value in getattr(gui, "_manual_motion_direction", {}).values()):
        blockers.append("手動移動尚未結束")
    return list(dict.fromkeys(blockers))
