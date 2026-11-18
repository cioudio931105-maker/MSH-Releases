from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HARDWARE_DIR = PROJECT_ROOT / "hardware"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(HARDWARE_DIR) not in sys.path:
    sys.path.insert(0, str(HARDWARE_DIR))

from cell_identification.classify import load_model, top1_label
from arduino_stepper import ArduinoStepper


def main() -> int:
    p = argparse.ArgumentParser(description="Classify an image then move stepper based on label")
    p.add_argument("--image", required=True, help="Image path to classify")
    p.add_argument("--model", default="yolov8n-cls.pt", help="YOLO classification model path")
    p.add_argument("--port", required=True, help="Arduino serial port, e.g. COM3")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--speed_us", type=int, default=800, help="STEP/DIR firmware speed (microseconds)")
    p.add_argument("--speed_ms", type=int, default=0, help="28BYJ-48 ULN2003 firmware speed (ms per half-step)")
    p.add_argument("--steps_one", type=int, default=200)
    p.add_argument("--steps_two", type=int, default=400)
    p.add_argument("--steps_three", type=int, default=600)
    args = p.parse_args()

    model = load_model(args.model)
    label = top1_label(model, args.image)
    print("Top1 label:", label)

    steps_map = {
        "one": args.steps_one,
        "two": args.steps_two,
        "three": args.steps_three,
    }

    if label not in steps_map:
        print("Label not in (one/two/three); no move.")
        return 0

    stepper = ArduinoStepper(port=args.port, baud=args.baud)
    stepper.connect()
    if not stepper.ping():
        print("Warning: no PONG received (check board/baud)")

    if args.speed_ms and args.speed_ms > 0:
        stepper.set_speed_ms(args.speed_ms)
    else:
        stepper.set_speed_us(args.speed_us)
    resp = stepper.move(steps_map[label])
    print(resp)
    stepper.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
