"""Production XY motion policy shared by every host-side movement path.

4096 is the existing nominal output-shaft half-step count, not a measured
platform displacement. The matching X/Y continuous firmware enforces this
interval independently of the host and rejects other speeds.
"""

import math

FIXED_MOTOR_RPM = 0.02
HALF_STEPS_PER_OUTPUT_REV = 4096
FIXED_STEP_INTERVAL_US = round(60_000_000 / (FIXED_MOTOR_RPM * HALF_STEPS_PER_OUTPUT_REV))
FIXED_STEP_DELAY_MS = round(FIXED_STEP_INTERVAL_US / 1000)
FIXED_STEP_DELAY_S = FIXED_STEP_INTERVAL_US / 1_000_000
FIXED_STEPS_PER_SECOND = 1.0 / FIXED_STEP_DELAY_S
LEGACY_PRELOAD_ENABLED = False
MOTION_POLICY_REPLY = (
    f"MOTION_POLICY RPM={FIXED_MOTOR_RPM:.3f} "
    f"STEPS_PER_REV={HALF_STEPS_PER_OUTPUT_REV} "
    f"STEP_US={FIXED_STEP_INTERVAL_US} PRELOAD=OFF"
)


def require_fixed_rpm(rpm: float) -> None:
    if not math.isfinite(float(rpm)) or not math.isclose(float(rpm), FIXED_MOTOR_RPM, rel_tol=0, abs_tol=1e-9):
        raise ValueError("All production motion is fixed at 0.02 RPM.")
