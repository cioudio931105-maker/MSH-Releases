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
    p = argparse.ArgumentParser(description="Stepper control over Serial (manual jog or auto loop)")
    p.add_argument("--port", default="", help="Arduino serial port, e.g. COM6 (leave empty for auto-select)")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--speed_ms", type=int, default=5, help="28BYJ-48 ULN2003: ms per half-step")
    p.add_argument("--step", type=int, default=16, help="Jog step size (half-steps)")
    p.add_argument("--warmup", action="store_true", help="Run small +/- preload moves before jogging")
    p.add_argument("--warmup_steps", type=int, default=6)
    p.add_argument("--warmup_cycles", type=int, default=2)
    p.add_argument("--fixed_approach", action="store_true", help="End jog moves from a fixed direction")
    p.add_argument("--approach_direction", type=int, default=1, choices=[-1, 1])
    p.add_argument("--approach_preload_steps", type=int, default=6)
    p.add_argument("--settle_ms", type=int, default=250)
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
    speed_ms = int(args.speed_ms)

    port = _resolve_port(args.port)
    if port is None:
        return 2

    stepper = ArduinoStepper(port=port, baud=args.baud)
    try:
        stepper.connect()
    except Exception as exc:
        print(f"Failed to open serial port {port}: {exc}")
        return 2
    stepper.set_speed_ms(speed_ms)
    stepper.default_settle_s = max(0.0, int(args.settle_ms) / 1000.0)

    try:
        if args.warmup:
            stepper.warmup(steps=args.warmup_steps, cycles=args.warmup_cycles)
        if args.auto:
            print("Auto move ready")
            print(
                f"Port={port}  speed_ms={speed_ms}  step={step_size}  "
                f"cycles={args.cycles}  interval_ms={args.interval_ms}  "
                f"direction={args.direction}  pingpong={int(args.pingpong)}"
            )
            print("Press Ctrl+C to stop.")
            t0 = time.time()
            if args.fixed_approach:
                moves_done = 0
                dir_sign = 1 if int(args.direction) >= 0 else -1
                try:
                    while True:
                        move_steps = step_size * dir_sign
                        resp = stepper.move_with_fixed_approach(
                            move_steps,
                            approach_direction=args.approach_direction,
                            preload_steps=args.approach_preload_steps,
                        )
                        _print_move(move_steps, resp)
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

        print("Manual jog ready")
        print(f"Port={port}  speed_ms={speed_ms}  step={step_size}")
        print("Keys: n=+step, p=-step, +=step+1, -=step-1, ]=faster, [=slower, q=quit")

        while True:
            if not msvcrt.kbhit():
                time.sleep(0.02)
                continue

            ch = msvcrt.getwch()
            if ch in ("q", "Q"):
                break

            if ch == "n":
                print(f"MOVE +{step_size}")
                if args.fixed_approach:
                    print(
                        stepper.move_with_fixed_approach(
                            step_size,
                            approach_direction=args.approach_direction,
                            preload_steps=args.approach_preload_steps,
                        )
                    )
                else:
                    print(stepper.move_stabilized(step_size))
                continue

            if ch == "p":
                print(f"MOVE -{step_size}")
                if args.fixed_approach:
                    print(
                        stepper.move_with_fixed_approach(
                            -step_size,
                            approach_direction=args.approach_direction,
                            preload_steps=args.approach_preload_steps,
                        )
                    )
                else:
                    print(stepper.move_stabilized(-step_size))
                continue

            if ch == "+":
                step_size += 1
                print(f"step={step_size}")
                continue

            if ch == "-":
                step_size = max(1, step_size - 1)
                print(f"step={step_size}")
                continue

            if ch == "]":
                speed_ms = max(1, speed_ms - 1)
                stepper.set_speed_ms(speed_ms)
                print(f"speed_ms={speed_ms} (faster)")
                continue

            if ch == "[":
                speed_ms = min(20, speed_ms + 1)
                stepper.set_speed_ms(speed_ms)
                print(f"speed_ms={speed_ms} (slower)")
                continue
    finally:
        stepper.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
