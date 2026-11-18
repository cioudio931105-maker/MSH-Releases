from __future__ import annotations

import argparse
import os
import time
from datetime import datetime
from typing import Optional, Tuple

import cv2

from arduino_stepper import ArduinoStepper

_PREVIEW_MAX_WIDTH = 960
_BASLER_PREVIEW_FPS = 20.0
_BASLER_PREVIEW_EXPOSURE_UPPER_US = 50000.0
_BASLER_PREVIEW_EXPOSURE_LOWER_US = 100.0


def _save_frame(frame, out_dir: str, prefix: str = "cap") -> str:
    os.makedirs(out_dir, exist_ok=True)
    fname = f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.jpg"
    path = os.path.join(out_dir, fname)
    cv2.imwrite(path, frame)
    return path


def _sharpness_score(frame) -> float:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _prepare_preview_frame(frame, max_width: int = _PREVIEW_MAX_WIDTH):
    if frame is None:
        return frame

    h, w = frame.shape[:2]
    if w <= max_width:
        return frame

    scale = max_width / float(w)
    out_h = max(1, int(h * scale))
    return cv2.resize(frame, (max_width, out_h), interpolation=cv2.INTER_AREA)


def _set_pylon_value_if_available(camera: object, attr_name: str, value) -> None:
    try:
        node = getattr(camera, attr_name)
    except Exception:
        return
    if node is None:
        return
    try:
        if hasattr(node, "SetValue"):
            node.SetValue(value)
    except Exception:
        pass


def _configure_basler_preview_camera(camera: object) -> None:
    _set_pylon_value_if_available(camera, "TriggerSelector", "FrameStart")
    _set_pylon_value_if_available(camera, "TriggerMode", "Off")
    _set_pylon_value_if_available(camera, "AcquisitionMode", "Continuous")
    _set_pylon_value_if_available(camera, "ExposureMode", "Timed")
    _set_pylon_value_if_available(camera, "ExposureAuto", "Continuous")
    _set_pylon_value_if_available(camera, "GainAuto", "Continuous")
    _set_pylon_value_if_available(camera, "BalanceWhiteAuto", "Continuous")
    _set_pylon_value_if_available(camera, "AutoExposureTimeLowerLimit", _BASLER_PREVIEW_EXPOSURE_LOWER_US)
    _set_pylon_value_if_available(camera, "AutoExposureTimeUpperLimit", _BASLER_PREVIEW_EXPOSURE_UPPER_US)
    _set_pylon_value_if_available(camera, "AcquisitionFrameRateEnable", True)
    _set_pylon_value_if_available(camera, "AcquisitionFrameRate", _BASLER_PREVIEW_FPS)


def _build_camera_backends() -> list[tuple[str, Optional[int]]]:
    backends: list[tuple[str, Optional[int]]] = []
    if hasattr(cv2, "CAP_DSHOW"):
        backends.append(("DSHOW", cv2.CAP_DSHOW))
    if hasattr(cv2, "CAP_MSMF"):
        backends.append(("MSMF", cv2.CAP_MSMF))
    backends.append(("DEFAULT", None))
    return backends


def _candidate_camera_indices(preferred_index: int, scan_max: int) -> list[int]:
    indices: list[int] = []
    if preferred_index >= 0:
        indices.append(preferred_index)

    for idx in range(1, max(1, scan_max) + 1):
        if idx not in indices:
            indices.append(idx)

    if 0 not in indices:
        indices.append(0)

    return indices


def _try_open_camera(
    camera_index: int,
    backend_name: str,
    backend: Optional[int],
    warmup_reads: int = 3,
) -> tuple[Optional[cv2.VideoCapture], str]:
    cap = cv2.VideoCapture(camera_index, backend) if backend is not None else cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        cap.release()
        return None, f"{camera_index}:{backend_name}:open_failed"

    for attempt in range(warmup_reads):
        ret, frame = cap.read()
        if ret and frame is not None:
            return cap, f"{camera_index}:{backend_name}:ok"
        time.sleep(0.1 if attempt == 0 else 0.05)

    cap.release()
    return None, f"{camera_index}:{backend_name}:no_frame"


def _open_opencv_camera(camera_index: int, scan_max: int) -> tuple[Optional[cv2.VideoCapture], Optional[int], Optional[str], list[str]]:
    tried: list[str] = []
    for idx in _candidate_camera_indices(camera_index, scan_max):
        for backend_name, backend in _build_camera_backends():
            cap, status = _try_open_camera(idx, backend_name, backend)
            tried.append(status)
            if cap is not None:
                return cap, idx, backend_name, tried
    return None, None, None, tried


def _list_opencv_cameras(camera_index: int, scan_max: int) -> int:
    found: list[str] = []
    for idx in _candidate_camera_indices(camera_index, scan_max):
        for backend_name, backend in _build_camera_backends():
            cap, status = _try_open_camera(idx, backend_name, backend, warmup_reads=2)
            if cap is not None:
                found.append(f"index={idx} backend={backend_name}")
                cap.release()
            else:
                print(f"[camera-scan] {status}")

    if found:
        print("Detected OpenCV cameras:")
        for item in found:
            print(f"  {item}")
        return 0

    print("No OpenCV cameras detected.")
    print("Suggestions:")
    print("  1) Close Camera / Zoom / Teams / browser tabs that may lock the device.")
    print("  2) Replug the USB camera and confirm Windows Device Manager can see it.")
    print("  3) On Windows, check Settings > Privacy & security > Camera.")
    print("  4) If this is a Basler camera, use --pylon_list or --pylon instead of OpenCV.")
    return 2


def main() -> int:
    p = argparse.ArgumentParser(
        description="Move stepper and capture frames (28BYJ-48 / ULN2003)"
    )
    p.add_argument("--port", default="COM7", help="Arduino serial port, e.g. COM7")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--speed_ms", type=int, default=5, help="28BYJ-48: ms per half-step")
    p.add_argument("--steps", type=int, default=16, help="Steps per jog (can be negative)")
    p.add_argument("--settle_ms", type=int, default=200, help="Wait after move before capture")
    p.add_argument("--warmup", action="store_true", help="Run small +/- preload moves before capture movement")
    p.add_argument("--warmup_steps", type=int, default=6)
    p.add_argument("--warmup_cycles", type=int, default=2)
    p.add_argument("--fixed_approach", action="store_true", help="End every move from a fixed direction")
    p.add_argument("--approach_direction", type=int, default=1, choices=[-1, 1])
    p.add_argument("--approach_preload_steps", type=int, default=6)
    p.add_argument("--camera", type=int, default=0, help="OpenCV camera index")
    p.add_argument("--camera_scan_max", type=int, default=10, help="Highest OpenCV camera index to scan")
    p.add_argument("--list_cameras", action="store_true", help="List OpenCV cameras and exit")
    p.add_argument("--out_dir", default="captured_steps", help="Output folder")
    p.add_argument("--auto", action="store_true", help="Run automatic move + capture loop")
    p.add_argument("--cycles", type=int, default=0, help="Auto moves count (0=forever)")
    p.add_argument("--interval_ms", type=int, default=200, help="Pause between auto moves")
    p.add_argument(
        "--direction",
        type=int,
        default=1,
        choices=[-1, 1],
        help="Auto direction (1=forward, -1=reverse)",
    )
    p.add_argument(
        "--pingpong",
        action="store_true",
        help="Auto mode: alternate direction each move",
    )
    p.add_argument("--pylon", action="store_true", help="Force Basler pypylon camera")
    p.add_argument("--opencv", action="store_true", help="Use OpenCV camera instead of Basler")
    p.add_argument("--pylon_serial", default="", help="Basler camera serial number (optional)")
    p.add_argument("--pylon_timeout_ms", type=int, default=2000, help="Pylon grab timeout in ms")
    p.add_argument("--pylon_list", action="store_true", help="List detected Basler cameras and exit")
    p.add_argument(
        "--updown_once",
        action="store_true",
        help="Run one up/down cycle: up->capture, down->capture",
    )
    p.add_argument("--no_preview", action="store_true", help="Disable preview window")
    p.add_argument(
        "--no_stepper",
        action="store_true",
        help="Run camera preview without requiring stepper connection",
    )
    p.add_argument(
        "--capture_first",
        action="store_true",
        help="Auto mode: capture one frame before the first move",
    )
    p.add_argument(
        "--autofocus",
        action="store_true",
        help="Enable hardware autofocus (OpenCV camera only) and sharpness checks",
    )
    p.add_argument(
        "--autofocus_settle_ms",
        type=int,
        default=250,
        help="Wait time before each autofocus capture attempt",
    )
    p.add_argument(
        "--sharpness_threshold",
        type=float,
        default=120.0,
        help="Laplacian variance threshold. Higher means stricter sharpness requirement.",
    )
    p.add_argument(
        "--sharpness_retries",
        type=int,
        default=5,
        help="Retry count when captured frame is below sharpness threshold",
    )
    p.add_argument(
        "--sharpness_retry_interval_ms",
        type=int,
        default=120,
        help="Delay between sharpness retries",
    )
    args = p.parse_args()

    if args.no_preview and not (args.auto or args.updown_once):
        print("Interactive manual mode requires preview. Remove --no_preview or use --auto/--updown_once.")
        return 2

    stepper = None
    if args.auto and args.no_stepper:
        print("Auto mode requires stepper connection. Remove --no_stepper to run auto mode.")
        return 2
    requires_stepper = not args.no_stepper and not args.pylon_list and not args.list_cameras
    cap = None
    pylon = None
    pylon_camera = None
    pylon_converter = None
    autofocus_enabled = False
    use_pylon = not args.opencv and not args.list_cameras
    if args.pylon or args.pylon_list or args.pylon_serial:
        use_pylon = True
    try:
        if requires_stepper:
            stepper = ArduinoStepper(port=args.port, baud=args.baud)
            stepper.connect()
            stepper.set_speed_ms(args.speed_ms)
            stepper.default_settle_s = max(0.0, args.settle_ms / 1000.0)
            if args.warmup:
                stepper.warmup(steps=args.warmup_steps, cycles=args.warmup_cycles)

        if use_pylon:
            try:
                from pypylon import pylon as pylon_mod
            except Exception as exc:
                print(f"Failed to import pypylon: {exc}")
                return 2
            pylon = pylon_mod
            tl_factory = pylon.TlFactory.GetInstance()
            devices = tl_factory.EnumerateDevices()
            if devices:
                print("Detected Basler cameras:")
                for idx, dev in enumerate(devices):
                    vendor = dev.GetVendorName()
                    model = dev.GetModelName()
                    serial = dev.GetSerialNumber()
                    user = dev.GetUserDefinedName()
                    print(f"  [{idx}] vendor={vendor} model={model} serial={serial} name={user}")
            else:
                print("No Basler cameras detected.")
                print("Suggestions:")
                print("  1) Close Pylon Viewer if it is open (camera may be locked).")
                print("  2) Replug USB cable and confirm device appears in Pylon Viewer.")
                print("  3) If multiple interfaces exist, confirm the correct one is enabled.")
                print("  4) Run with --pylon_list after reconnecting to verify detection.")

            if args.pylon_list:
                return 0
            if not devices:
                return 2

            if args.pylon_serial:
                match = None
                for dev in devices:
                    if dev.GetSerialNumber() == args.pylon_serial:
                        match = dev
                        break
                if match is None:
                    print(f"Pylon device not found: serial={args.pylon_serial}")
                    return 2
                pylon_camera = pylon.InstantCamera(tl_factory.CreateDevice(match))
            else:
                pylon_camera = pylon.InstantCamera(tl_factory.CreateFirstDevice())
            pylon_camera.Open()
            _configure_basler_preview_camera(pylon_camera)
            pylon_converter = pylon.ImageFormatConverter()
            pylon_converter.OutputPixelFormat = pylon.PixelType_BGR8packed
            pylon_converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned
            pylon_camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
            try:
                print(
                    "Basler preview mode: "
                    f"target_fps={_BASLER_PREVIEW_FPS:.0f} "
                    f"exposure_upper_us={_BASLER_PREVIEW_EXPOSURE_UPPER_US:.0f}"
                )
            except Exception:
                pass
        else:
            if args.list_cameras:
                return _list_opencv_cameras(args.camera, args.camera_scan_max)

            cap, opened_index, backend_name, tried = _open_opencv_camera(args.camera, args.camera_scan_max)
            if cap is None:
                print("Failed to open camera.")
                print("Tried:")
                for item in tried[:12]:
                    print(f"  {item}")
                if len(tried) > 12:
                    print(f"  ... and {len(tried) - 12} more")
                print("Suggestions:")
                print("  1) Try --list_cameras to see which index/backend is available.")
                print("  2) Try --camera 1 or a higher index if this is an external USB camera.")
                print("  3) Close other apps that may be using the camera.")
                print("  4) If this is a Basler camera, use --pylon_list or --pylon.")
                return 2
            print(f"Opened camera: index={opened_index} backend={backend_name}")
            if args.autofocus:
                ok = cap.set(cv2.CAP_PROP_AUTOFOCUS, 1)
                print(f"OpenCV autofocus requested: {'OK' if ok else 'unsupported'}")
                autofocus_enabled = bool(ok)

        preview = not args.no_preview
        settle_s = max(0.0, args.settle_ms / 1000.0)
        af_settle_s = max(0.0, args.autofocus_settle_ms / 1000.0)
        retry_wait_s = max(0.0, args.sharpness_retry_interval_ms / 1000.0)

        def read_frame():
            if use_pylon:
                try:
                    grab = pylon_camera.RetrieveResult(
                        args.pylon_timeout_ms, pylon.TimeoutHandling_ThrowException
                    )
                except Exception as exc:
                    print(f"Capture failed: {exc}")
                    return False, None
                try:
                    if not grab.GrabSucceeded():
                        return False, None
                    image = pylon_converter.Convert(grab)
                    frame = image.GetArray()
                    return True, frame
                finally:
                    grab.Release()
            return cap.read()

        def capture_best_focus(context: str) -> Tuple[bool, object, float]:
            retries = max(0, int(args.sharpness_retries))
            threshold = float(args.sharpness_threshold)
            best_frame = None
            best_score = -1.0
            for attempt in range(retries + 1):
                if autofocus_enabled and af_settle_s > 0:
                    time.sleep(af_settle_s)
                ok, frame = read_frame()
                if not ok or frame is None:
                    if attempt < retries and retry_wait_s > 0:
                        time.sleep(retry_wait_s)
                    continue

                score = _sharpness_score(frame)
                if score > best_score:
                    best_score = score
                    best_frame = frame

                if score >= threshold:
                    if attempt > 0:
                        print(
                            f"{context}: focus recovered at retry {attempt} "
                            f"(sharpness={score:.1f})"
                        )
                    return True, frame, score

                if attempt < retries and retry_wait_s > 0:
                    time.sleep(retry_wait_s)

            if best_frame is None:
                return False, None, -1.0
            return False, best_frame, best_score

        def print_sharpness_warning(score: float) -> None:
            print(
                f"Warning: below sharpness threshold "
                f"({score:.1f} < {args.sharpness_threshold:.1f}); saving best frame."
            )

        def capture_after_move(move_steps: int) -> None:
            if settle_s > 0:
                time.sleep(settle_s)
            ret2, frame2, score = capture_best_focus(f"After move {move_steps}")
            if frame2 is None:
                print("Capture failed after move.")
                return
            if not ret2:
                print_sharpness_warning(score)
            path = _save_frame(frame2, args.out_dir, prefix=f"step_{move_steps}")
            print(f"Saved {path}  sharpness={score:.1f}")
            if preview:
                cv2.imshow("move_and_capture", _prepare_preview_frame(frame2))
                cv2.waitKey(1)

        def move_stepper(move_steps: int) -> str:
            if stepper is None:
                raise RuntimeError("stepper is not connected")
            if args.fixed_approach:
                return stepper.move_with_fixed_approach(
                    move_steps,
                    approach_direction=args.approach_direction,
                    preload_steps=args.approach_preload_steps,
                    settle_s=0.03,
                )
            return stepper.move_stabilized(move_steps, settle_s=0.0)

        def capture_now(prefix: str = "cap", fail_message: str = "Capture failed.") -> None:
            ret2, frame2, score = capture_best_focus(prefix)
            if frame2 is None:
                print(fail_message)
                return
            if not ret2:
                print_sharpness_warning(score)
            path = _save_frame(frame2, args.out_dir, prefix=prefix)
            print(f"Saved {path}  sharpness={score:.1f}")
            if preview:
                cv2.imshow("move_and_capture", _prepare_preview_frame(frame2))
                cv2.waitKey(1)

        if args.updown_once:
            if stepper is None:
                print("Up/down once requires stepper connection. Remove --no_stepper.")
                return 2
            if args.steps == 0:
                print("Up/down once requires --steps (step size).")
                return 2
            print("Up/down once: up->capture, down->capture")
            print(f"steps={args.steps} settle_ms={args.settle_ms} preview={int(preview)}")
            step_size = abs(int(args.steps))
            move_stepper(step_size)
            capture_after_move(step_size)
            move_stepper(-step_size)
            capture_after_move(-step_size)
            return 0

        if args.auto:
            if stepper is None:
                print("Auto mode requires stepper connection. Remove --no_stepper.")
                return 2
            print(
                "Auto move + capture ready: "
                f"steps={args.steps} cycles={args.cycles} interval_ms={args.interval_ms} "
                f"direction={args.direction} pingpong={int(args.pingpong)}"
            )
            print("Press Ctrl+C to stop.")

            if args.capture_first:
                capture_now(prefix="start")

            def on_move(move_steps: int, resp: str) -> None:
                if resp:
                    print(resp)
                capture_after_move(move_steps)

            t0 = time.time()
            if args.fixed_approach:
                moves_done = 0
                step_size = abs(int(args.steps))
                dir_sign = 1 if int(args.direction) >= 0 else -1
                if int(args.steps) < 0:
                    dir_sign *= -1
                try:
                    while True:
                        move_steps = step_size * dir_sign
                        resp = move_stepper(move_steps)
                        on_move(move_steps, resp)
                        moves_done += 1
                        if args.pingpong:
                            dir_sign *= -1
                        if int(args.cycles) > 0 and moves_done >= int(args.cycles):
                            break
                        if args.interval_ms > 0:
                            time.sleep(max(0.0, args.interval_ms / 1000.0))
                except KeyboardInterrupt:
                    pass
            else:
                moves_done = stepper.auto_move(
                    steps=args.steps,
                    cycles=int(args.cycles),
                    interval_s=max(0.0, args.interval_ms / 1000.0),
                    direction=int(args.direction),
                    pingpong=bool(args.pingpong),
                    on_move=on_move,
                )
            elapsed_s = time.time() - t0
            print(f"Auto done: moves={moves_done} elapsed_s={elapsed_s:.2f}")
        else:
            print("Manual move + capture ready.")
            print("Keys: n=move+capture, s=capture only, q=quit")
            while True:
                ret, frame = read_frame()
                if not ret:
                    print("Capture failed.")
                    break

                cv2.imshow("move_and_capture", _prepare_preview_frame(frame))
                key = cv2.waitKey(1) & 0xFF

                if key == ord("q"):
                    break

                if key == ord("s"):
                    capture_now(prefix="cap", fail_message="Capture failed.")

                if key == ord("n"):
                    if stepper is None:
                        print("Move command requires stepper connection. Remove --no_stepper.")
                        continue
                    try:
                        move_stepper(args.steps)
                    except Exception as e:
                        print(f"Move failed: {e}")
                        continue

                    if settle_s > 0:
                        time.sleep(settle_s)

                    capture_now(
                        prefix=f"step_{args.steps}",
                        fail_message="Capture failed after move.",
                    )
    finally:
        try:
            if pylon_camera is not None:
                try:
                    pylon_camera.StopGrabbing()
                finally:
                    pylon_camera.Close()
            if cap is not None:
                cap.release()
        finally:
            cv2.destroyAllWindows()
            if stepper is not None:
                stepper.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
