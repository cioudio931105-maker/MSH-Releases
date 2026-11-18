from __future__ import annotations

import argparse
import time

import msvcrt

from arduino_stepper import ArduinoStepper, list_serial_ports


def _print_move(move_steps: int, resp: str) -> None:
    print(f"MOVE {move_steps}")
    if resp:
        print(resp)


def _resolve_port(port_arg: str) -> str | None:
    port = (port_arg or "").strip()
    if port:
        return port

    ports = list_serial_ports()
    if not ports:
        print("No serial ports found. Connect device or use --port.")
        return None
    if len(ports) == 1:
        print(f"Auto-selected serial port: {ports[0]}")
        return ports[0]

    print("Multiple serial ports detected. Please specify --port explicitly:")
    for pth in ports:
        print(" ", pth)
    return None


def main() -> int:
    p = argparse.ArgumentParser(
        description="Stepper control over Serial (manual jog or auto loop)"
    )
    p.add_argument("--port", default="", help="Arduino serial port, e.g. COM7 (leave empty for auto-select)")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument(
        "--speed_us",
        type=int,
        default=800,
        help="Pulse delay in microseconds (smaller=faster)",
    )
    p.add_argument("--step", type=int, default=200, help="Jog step size (steps)")
    p.add_argument("--auto", action="store_true", help="Run automatic move loop")
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
    args = p.parse_args()

    step_size = int(args.step)
    speed_us = int(args.speed_us)

    port = _resolve_port(args.port)
    if port is None:
        return 2

    stepper = ArduinoStepper(port=port, baud=args.baud)
    try:
        stepper.connect()
    except Exception as exc:
        print(f"Failed to open serial port {port}: {exc}")
        return 2

    ok = stepper.ping()
    if not ok:
        print("Warning: no PONG received (check board/baud/port)")

    stepper.set_speed_us(speed_us)

    try:
        if args.auto:
            print("Auto move ready (STEP/DIR)")
            print(
                f"Port={port}  speed_us={speed_us}  step={step_size}  "
                f"cycles={args.cycles}  interval_ms={args.interval_ms}  "
                f"direction={args.direction}  pingpong={int(args.pingpong)}"
            )
            print("Press Ctrl+C to stop.")
            t0 = time.time()
            moves_done = stepper.auto_move(
                steps=step_size,
                cycles=int(args.cycles),
                interval_s=max(0.0, args.interval_ms / 1000.0),
                direction=int(args.direction),
                pingpong=bool(args.pingpong),
                on_move=_print_move,
            )
            elapsed_s = time.time() - t0
            print(f"Auto done: moves={moves_done} elapsed_s={elapsed_s:.2f}")
            return 0

        print("Manual jog ready (STEP/DIR)")
        print(f"Port={port}  speed_us={speed_us}  step={step_size}")
        print(
            "Keys: n=+step, p=-step, +=step+10, -=step-10, ]=faster, [=slower, q=quit"
        )

        while True:
            if not msvcrt.kbhit():
                time.sleep(0.02)
                continue

            ch = msvcrt.getwch()
            if ch in ("q", "Q"):
                break

            if ch == "n":
                print(f"MOVE +{step_size}")
                print(stepper.move(step_size))
                continue

            if ch == "p":
                print(f"MOVE -{step_size}")
                print(stepper.move(-step_size))
                continue

            if ch == "+":
                step_size += 10
                print(f"step={step_size}")
                continue

            if ch == "-":
                step_size = max(1, step_size - 10)
                print(f"step={step_size}")
                continue

            if ch == "]":
                speed_us = max(50, speed_us - 50)
                stepper.set_speed_us(speed_us)
                print(f"speed_us={speed_us} (faster)")
                continue

            if ch == "[":
                speed_us = min(5000, speed_us + 50)
                stepper.set_speed_us(speed_us)
                print(f"speed_us={speed_us} (slower)")
                continue
    finally:
        stepper.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
