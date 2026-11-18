from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

import os
import re
import time
import sys
from pathlib import Path

# Also support direct launches of the legacy hardware scripts.
_WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
if not getattr(sys, "frozen", False) and str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))
from msh_app.core.msh_motion_policy import (
    FIXED_MOTOR_RPM, FIXED_STEP_DELAY_MS, FIXED_STEP_INTERVAL_US,
    FIXED_STEP_DELAY_S, LEGACY_PRELOAD_ENABLED, MOTION_POLICY_REPLY,
    require_fixed_rpm,
)

try:
    import serial
    from serial.tools import list_ports
    _SERIAL_WRITE_EXCEPTIONS = (PermissionError, serial.SerialException)
except Exception:  # pragma: no cover - optional during helper-only tests
    serial = None  # type: ignore[assignment]
    list_ports = None  # type: ignore[assignment]
    _SERIAL_WRITE_EXCEPTIONS = (PermissionError,)


@dataclass(frozen=True)
class SerialPortInfo:
    device: str
    description: str = ""
    hwid: str = ""


@dataclass(frozen=True)
class MotionStatus:
    state: str
    requested_steps: int
    executed_steps: int
    remaining_steps: int

    @property
    def is_active(self) -> bool:
        return self.state in {"RUNNING", "PAUSED"}

    @property
    def is_paused(self) -> bool:
        return self.state == "PAUSED"


def _port_sort_key(port: str) -> tuple[int, int | str]:
    match = re.fullmatch(r"COM(\d+)", str(port).strip(), flags=re.IGNORECASE)
    if match:
        return (0, int(match.group(1)))
    return (1, str(port).upper())


def _list_serial_ports_pyserial() -> list[SerialPortInfo]:
    if list_ports is None:
        return []
    infos: list[SerialPortInfo] = []
    for port in list_ports.comports():
        infos.append(
            SerialPortInfo(
                device=str(getattr(port, "device", "") or ""),
                description=str(getattr(port, "description", "") or ""),
                hwid=str(getattr(port, "hwid", "") or ""),
            )
        )
    return [info for info in infos if info.device]


def _list_serial_ports_windows_registry() -> list[SerialPortInfo]:
    if os.name != "nt":
        return []
    try:
        import winreg
    except Exception:
        return []

    ports: list[SerialPortInfo] = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DEVICEMAP\SERIALCOMM") as key:
            index = 0
            while True:
                try:
                    _name, value, _value_type = winreg.EnumValue(key, index)
                except OSError:
                    break
                device = str(value or "").strip()
                if device:
                    ports.append(SerialPortInfo(device=device))
                index += 1
    except Exception:
        return []
    return ports


def list_serial_port_infos() -> list[SerialPortInfo]:
    merged: dict[str, SerialPortInfo] = {}
    for info in [*_list_serial_ports_pyserial(), *_list_serial_ports_windows_registry()]:
        device = str(info.device).strip()
        if not device:
            continue
        key = device.upper()
        existing = merged.get(key)
        if existing is None:
            merged[key] = SerialPortInfo(device=device, description=info.description, hwid=info.hwid)
            continue
        description = existing.description or info.description
        hwid = existing.hwid or info.hwid
        merged[key] = SerialPortInfo(device=existing.device, description=description, hwid=hwid)
    return sorted(merged.values(), key=lambda item: _port_sort_key(item.device))


def list_serial_ports() -> list[str]:
    return [info.device for info in list_serial_port_infos()]


@dataclass
class ArduinoStepper:
    port: str
    baud: int = 115200
    timeout_s: float = 2.0
    boot_wait_s: float = 2.0
    backlash_steps: int = 0
    default_settle_s: float = 0.25
    warmup_steps: int = 80
    warmup_cycles: int = 0
    _supports_motor_id: bool = False

    _ser: Optional[serial.Serial] = None
    _backlash_steps_by_motor: dict[int, int] = field(default_factory=dict)
    _last_direction_by_motor: dict[int, int] = field(default_factory=dict)
    _speed_delay_s_by_motor: dict[int, float] = field(default_factory=dict)

    def _open_serial(self) -> None:
        if serial is None:
            raise RuntimeError("pyserial is not installed; serial motor control is unavailable.")
        if self._ser:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None

        self._ser = serial.Serial(self.port, self.baud, timeout=self.timeout_s)

    def connect(self, *, initialize_speed: bool = True, probe_capabilities: bool = True) -> None:
        """Open only a controller advertising the fixed production policy.

        The legacy keyword arguments are retained for callers, but cannot
        bypass the read-only contract check or enable a speed-changing probe.
        """
        if self._ser and self._ser.is_open:
            return
        self._open_serial()
        time.sleep(self.boot_wait_s)
        self._ser.reset_input_buffer()
        self._ser.reset_output_buffer()
        self._last_direction_by_motor.clear()
        self._supports_motor_id = False
        try:
            self._write("MOTION_POLICY", _retry=False)
            response = self._wait_for_final_response(("MOTION_POLICY ",))
            if response != MOTION_POLICY_REPLY:
                raise RuntimeError(f"Incompatible motion policy: {response!r}")
        except Exception:
            # No motion or settings commands may be sent to an unknown board.
            self._ser.close()
            self._ser = None
            raise
        self._speed_delay_s_by_motor[0] = FIXED_STEP_DELAY_S

    def close(self) -> None:
        if self._ser:
            try:
                if self._ser.is_open:
                    try:
                        # Closing a link must never leave a hold-current command
                        # active indefinitely. Manual button release uses STOP to
                        # hold position; connection shutdown explicitly releases.
                        self._write("RELEASE", _retry=False)
                        self._ser.flush()
                    except Exception:
                        pass
                self._ser.close()
            finally:
                self._ser = None
        self._last_direction_by_motor.clear()

    def _readline(self) -> str:
        if not self._ser or not self._ser.is_open:
            raise RuntimeError("Not connected")
        raw = self._ser.readline()
        if not raw:
            return ""
        try:
            return raw.decode("utf-8", errors="replace").strip()
        except Exception:
            return str(raw)

    def _write(self, line: str, _retry: bool = True) -> None:
        if not self._ser:
            raise RuntimeError("Not connected")
        if not line.endswith("\n"):
            line += "\n"
        try:
            self._ser.write(line.encode("utf-8"))
            self._ser.flush()
        except _SERIAL_WRITE_EXCEPTIONS as exc:
            if not _retry:
                raise RuntimeError(f"Serial write failed on {self.port}: {exc}") from exc
            try:
                self.connect()
            except Exception:
                raise RuntimeError(f"Serial write failed on {self.port}: {exc}") from exc
            self._write(line, _retry=False)

    def ping(self) -> bool:
        self._write("PING")
        t0 = time.time()
        while time.time() - t0 < self.timeout_s:
            resp = self._readline()
            if not resp:
                continue
            if resp == "PONG":
                return True
        return False

    def set_speed_us(self, micros: int) -> None:
        if float(micros) != FIXED_STEP_INTERVAL_US:
            raise ValueError("All production motion is fixed at 0.02 RPM.")
        self.set_fixed_speed()

    def set_fixed_speed(self) -> None:
        self._write_and_wait_ok(f"SPEED_RPM {FIXED_MOTOR_RPM:.3f}")
        self._speed_delay_s_by_motor[0] = FIXED_STEP_DELAY_S

    def _initialize_motor_speeds_ms(self, ms: int) -> None:
        if self._supports_motor_id:
            self.set_speed_ms(ms, motor_id=0)
            self.set_speed_ms(ms, motor_id=1)
        else:
            self.set_speed_ms(ms)

    def set_speed_ms(self, ms: int, motor_id: int | None = None) -> None:
        if float(ms) != FIXED_STEP_DELAY_MS:
            raise ValueError("All production motion is fixed at 0.02 RPM.")
        value = FIXED_STEP_DELAY_MS
        if not self._supports_motor_id:
            if motor_id is not None and motor_id != 0:
                raise RuntimeError("Legacy firmware only supports motor 0 on this serial link.")
            self._write_and_wait_ok(f"SPEED_MS {value}")
            self._speed_delay_s_by_motor[0] = value / 1000.0
            return

        if motor_id is None:
            self._write_and_wait_ok(f"SPEED_MS {value}")
            self._speed_delay_s_by_motor[0] = value / 1000.0
        else:
            motor_key = self._resolve_motor_key(motor_id)
            self._write_and_wait_ok(f"SPEED_MS {int(motor_id)} {value}")
            self._speed_delay_s_by_motor[motor_key] = value / 1000.0

    def run_continuous(self, direction: int, rpm: float) -> str:
        require_fixed_rpm(rpm)
        direction_text = "CW" if int(direction) >= 0 else "CCW"
        return self._write_and_wait_ok(f"RUN {direction_text} {FIXED_MOTOR_RPM:.3f}")

    def release(self) -> str:
        return self._write_and_wait_ok("RELEASE")

    def enable(self, enabled: bool) -> None:
        self._write(f"ENABLE {1 if enabled else 0}")

    def _wait_for_final_response(self, accepted_prefixes: tuple[str, ...], timeout_s: float | None = None) -> str:
        timeout = self.timeout_s if timeout_s is None else max(0.1, float(timeout_s))
        t0 = time.time()
        last_resp = ""
        while time.time() - t0 < timeout:
            resp = self._readline()
            if not resp:
                continue
            last_resp = resp
            if resp.startswith("ERR"):
                raise RuntimeError(resp)
            if any(resp.startswith(prefix) for prefix in accepted_prefixes):
                return resp
            if resp in {"OK STOPPED", "OK RELEASED"}:
                raise RuntimeError("Motion interrupted before completion.")
        raise TimeoutError(f"Timed out waiting for {accepted_prefixes}; last response={last_resp!r}")

    def _write_and_wait_ok(self, line: str, timeout_s: float | None = None) -> str:
        self._write(line)
        return self._wait_for_final_response(("OK",), timeout_s=timeout_s)

    def stop(self, motor_id: int | None = None) -> str:
        if motor_id is None or not self._supports_motor_id:
            line = "STOP"
        else:
            line = f"STOP {int(motor_id)}"
        return self._write_and_wait_ok(line)

    def request_stop(self, motor_id: int | None = None) -> None:
        if motor_id is None or not self._supports_motor_id:
            line = "STOP"
        else:
            line = f"STOP {int(motor_id)}"
        self._write(line)

    def pause_motion(self, motor_id: int | None = None) -> str:
        if motor_id is None or not self._supports_motor_id:
            line = "PAUSE"
        else:
            line = f"PAUSE {int(motor_id)}"
        return self._write_and_wait_ok(line)

    def resume_motion(self, motor_id: int | None = None) -> str:
        if motor_id is None or not self._supports_motor_id:
            line = "RESUME"
        else:
            line = f"RESUME {int(motor_id)}"
        return self._write_and_wait_ok(line)

    def motion_status(self, motor_id: int | None = None) -> MotionStatus:
        if motor_id is None or not self._supports_motor_id:
            line = "STATUS"
        else:
            line = f"STATUS {int(motor_id)}"
        self._write(line)
        t0 = time.time()
        last_resp = ""
        while time.time() - t0 < self.timeout_s:
            resp = self._readline()
            if not resp:
                continue
            last_resp = resp
            if resp.startswith("ERR"):
                raise RuntimeError(resp)
            if not resp.startswith("STATUS "):
                continue
            parts = resp.split()
            if len(parts) != 5:
                raise RuntimeError(f"Invalid STATUS response from Arduino: {resp!r}")
            return MotionStatus(
                state=str(parts[1]).upper(),
                requested_steps=int(parts[2]),
                executed_steps=int(parts[3]),
                remaining_steps=int(parts[4]),
            )
        raise TimeoutError(f"Timed out waiting for STATUS from Arduino; last response={last_resp!r}")

    def start_move(
        self,
        steps: int,
        motor_id: int | None = None,
        apply_backlash: bool = False,
    ) -> None:
        self.move(
            int(steps),
            wait_done=False,
            motor_id=motor_id,
            apply_backlash=apply_backlash,
        )

    def set_hold(self, enabled: bool, motor_id: int | None = None) -> str:
        value = 1 if enabled else 0
        if motor_id is None and self._supports_motor_id:
            self._write_and_wait_ok(f"HOLD 0 {value}")
            return self._write_and_wait_ok(f"HOLD 1 {value}")
        if motor_id is None or not self._supports_motor_id:
            line = f"HOLD {value}"
        else:
            line = f"HOLD {int(motor_id)} {value}"
        return self._write_and_wait_ok(line)

    def set_direction_sign(self, sign: int, motor_id: int | None = None) -> str:
        value = 1 if int(sign) >= 0 else -1
        if motor_id is None or not self._supports_motor_id:
            line = f"DIR 0 {value}"
        else:
            line = f"DIR {int(motor_id)} {value}"
        return self._write_and_wait_ok(line)

    def calibrate_motion(self, steps: int = 80, motor_id: int | None = None) -> str:
        value = max(1, int(steps))
        if motor_id is None or not self._supports_motor_id:
            line = f"CALI {value}"
        else:
            line = f"CALI {int(motor_id)} {value}"
        self._write(line)
        return self._wait_for_final_response(("OK CALIBRATED",), timeout_s=self._move_timeout_s(value * 2, motor_id))

    def set_backlash_steps(self, steps: int, motor_id: int | None = None) -> None:
        value = max(0, int(steps))
        if not LEGACY_PRELOAD_ENABLED and value:
            raise ValueError("Backlash compensation is isolated from production motion.")
        if motor_id is None:
            self.backlash_steps = value
            return
        self._backlash_steps_by_motor[int(motor_id)] = value

    def _resolve_motor_key(self, motor_id: int | None) -> int:
        if motor_id is None or not self._supports_motor_id:
            return 0
        return int(motor_id)

    def _resolve_backlash_steps(self, motor_id: int | None) -> int:
        motor_key = self._resolve_motor_key(motor_id)
        return max(0, int(self._backlash_steps_by_motor.get(motor_key, self.backlash_steps)))

    def _move_timeout_s(self, steps: int, motor_id: int | None = None) -> float:
        delay_s = FIXED_STEP_DELAY_S
        expected_s = abs(int(steps)) * max(0.000001, delay_s)
        margin_s = max(15.0, expected_s * 0.35)
        return max(float(self.timeout_s), 30.0, expected_s + margin_s)

    def _compensated_move_steps(self, steps: int, motor_id: int | None = None) -> tuple[int, int]:
        requested_steps = int(steps)
        if requested_steps == 0:
            return 0, 0

        direction = 1 if requested_steps > 0 else -1
        motor_key = self._resolve_motor_key(motor_id)
        last_direction = self._last_direction_by_motor.get(motor_key)
        backlash_steps = self._resolve_backlash_steps(motor_id) if LEGACY_PRELOAD_ENABLED else 0
        compensated_steps = requested_steps
        if backlash_steps > 0 and last_direction is not None and last_direction != direction:
            compensated_steps += direction * backlash_steps
        return requested_steps, compensated_steps

    def reset_motion_state(self, motor_id: int | None = None) -> None:
        if motor_id is None:
            self._last_direction_by_motor.clear()
            return
        self._last_direction_by_motor.pop(self._resolve_motor_key(motor_id), None)

    def move(
        self,
        steps: int,
        wait_done: bool = True,
        motor_id: int | None = None,
        apply_backlash: bool = True,
    ) -> str:
        requested_steps = int(steps)
        if apply_backlash:
            requested_steps, compensated_steps = self._compensated_move_steps(steps, motor_id=motor_id)
        else:
            compensated_steps = requested_steps
        if motor_id is None or (motor_id == 0 and not self._supports_motor_id):
            self._write(f"MOVE {int(compensated_steps)}")
        elif motor_id == 1 and not self._supports_motor_id:
            raise RuntimeError("Legacy firmware on this serial link does not support motor 1.")
        else:
            self._write(f"MOVE {int(motor_id)} {int(compensated_steps)}")

        if not wait_done:
            if requested_steps != 0:
                self._last_direction_by_motor[self._resolve_motor_key(motor_id)] = 1 if requested_steps > 0 else -1
            return ""

        move_timeout_s = self._move_timeout_s(compensated_steps, motor_id=motor_id)
        t0 = time.time()
        while time.time() - t0 < move_timeout_s:
            resp = self._readline()
            if not resp:
                continue
            if resp.startswith("ERR"):
                raise RuntimeError(resp)
            if resp in {"OK STOPPED", "OK RELEASED"}:
                raise RuntimeError("MOVE interrupted before completion.")
            if resp.startswith("DONE"):
                if requested_steps != 0:
                    self._last_direction_by_motor[self._resolve_motor_key(motor_id)] = 1 if requested_steps > 0 else -1
                return resp
        raise TimeoutError(
            f"Timed out waiting for DONE from Arduino after {move_timeout_s:.1f}s "
            f"(steps={int(compensated_steps)})"
        )

    def warmup(
        self,
        steps: int | None = None,
        cycles: int | None = None,
        motor_id: int | None = None,
        interval_s: float = 0.05,
    ) -> None:
        if not LEGACY_PRELOAD_ENABLED:
            raise RuntimeError("Motor warmup is isolated; no fallback movements are allowed.")
        step_count = max(1, int(self.warmup_steps if steps is None else steps))
        cycle_count = max(0, int(self.warmup_cycles if cycles is None else cycles))
        if cycle_count == 0:
            return

        # New single-axis firmware supports a native net-zero preload command.
        # Fall back to explicit +/- moves so older boards still work.
        try:
            if motor_id is None or not self._supports_motor_id:
                self._write_and_wait_ok(f"WARMUP {step_count} {cycle_count}")
            else:
                self._write_and_wait_ok(f"WARMUP {int(motor_id)} {step_count} {cycle_count}")
            self.reset_motion_state(motor_id=motor_id)
            return
        except Exception:
            pass

        for _ in range(cycle_count):
            self.move(step_count, motor_id=motor_id, apply_backlash=False)
            if interval_s > 0:
                time.sleep(interval_s)
            self.move(-step_count, motor_id=motor_id, apply_backlash=False)
            if interval_s > 0:
                time.sleep(interval_s)

    def move_stabilized(
        self,
        steps: int,
        wait_done: bool = True,
        motor_id: int | None = None,
        apply_backlash: bool = True,
        settle_s: float | None = None,
    ) -> str:
        resp = self.move(
            steps,
            wait_done=wait_done,
            motor_id=motor_id,
            apply_backlash=apply_backlash,
        )
        delay = self.default_settle_s if settle_s is None else max(0.0, float(settle_s))
        if wait_done and delay > 0 and int(steps) != 0:
            time.sleep(delay)
        return resp

    def move_with_fixed_approach(
        self,
        steps: int,
        approach_direction: int = 1,
        preload_steps: int = 6,
        wait_done: bool = True,
        motor_id: int | None = None,
        settle_s: float | None = None,
    ) -> str:
        requested_steps = int(steps)
        if requested_steps == 0:
            return ""
        if not LEGACY_PRELOAD_ENABLED:
            return self.move_stabilized(
                requested_steps, wait_done=wait_done, motor_id=motor_id,
                apply_backlash=False, settle_s=settle_s,
            )

        approach = 1 if int(approach_direction) >= 0 else -1
        direction = 1 if requested_steps > 0 else -1
        preload = max(0, int(preload_steps))
        delay = self.default_settle_s if settle_s is None else max(0.0, float(settle_s))

        if preload <= 0 or direction == approach:
            return self.move_stabilized(
                requested_steps,
                wait_done=wait_done,
                motor_id=motor_id,
                apply_backlash=False,
                settle_s=delay,
            )

        overshoot_steps = requested_steps - approach * preload
        first_resp = self.move(
            overshoot_steps,
            wait_done=wait_done,
            motor_id=motor_id,
            apply_backlash=False,
        )
        if wait_done and delay > 0:
            time.sleep(delay)
        second_resp = self.move(
            approach * preload,
            wait_done=wait_done,
            motor_id=motor_id,
            apply_backlash=False,
        )
        if wait_done and delay > 0:
            time.sleep(delay)
        return f"{first_resp}; {second_resp}".strip("; ")

    def auto_move(
        self,
        steps: int,
        cycles: int = 0,
        interval_s: float = 0.0,
        direction: int = 1,
        pingpong: bool = False,
        motor_id: int | None = None,
        on_move: Optional[Callable[[int, str], None]] = None,
    ) -> int:
        if steps == 0:
            raise ValueError("steps must be non-zero")
        if direction not in (-1, 1):
            raise ValueError("direction must be -1 or 1")
        if cycles < 0:
            raise ValueError("cycles must be >= 0")

        moves_done = 0
        step_size = abs(int(steps))
        dir_sign = 1 if direction >= 0 else -1
        if steps < 0:
            dir_sign *= -1

        try:
            while True:
                move_steps = step_size * dir_sign
                resp = self.move(move_steps, motor_id=motor_id)
                moves_done += 1

                if on_move is not None:
                    on_move(move_steps, resp)

                if pingpong:
                    dir_sign *= -1

                if cycles > 0 and moves_done >= cycles:
                    break

                if interval_s > 0:
                    time.sleep(interval_s)
        except KeyboardInterrupt:
            pass

        return moves_done

    def _probe_motor_id_support(self) -> bool:
        # Production uses one verified fixed-policy controller per serial link.
        # Speed-writing capability probes are no longer used.
        return False
