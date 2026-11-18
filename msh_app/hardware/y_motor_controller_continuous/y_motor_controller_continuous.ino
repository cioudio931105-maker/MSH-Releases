// Arduino 28BYJ-48 + ULN2003 Serial Controller for Y-motor
// Single-axis version: one motor per Arduino
//
// Wiring:
//   IN1 -> D4
//   IN2 -> D5
//   IN3 -> D6
//   IN4 -> D7
//
// Protocol (newline terminated):
//   PING
//   MOVE <steps>         ; relative (can be negative)
//   SPEED_MS 732         ; compatibility alias for fixed 0.02 RPM
//   SPEED_RPM 0.020      ; only 0.02 output-shaft RPM is accepted
//   MOTION_POLICY       ; read-only fixed-speed/preload contract
//   FIRMWARE_ID         ; read-only version, assigned board label and topology
//   RUN CW [rpm]         ; continuous clockwise rotation
//   RUN CCW [rpm]        ; continuous counter-clockwise rotation
//   STOP                 ; stop and keep the current phase energized
//   RELEASE              ; stop and de-energize all coils
//   DIR <-1|1>           ; set direction sign
//   WARMUP [steps] [cycles] ; isolated: ERR PRELOAD_DISABLED, no movement
//   AUTOWARM <0|1>       ; only 0 allowed; automatic preload is isolated
//   WARMUP_STEPS <steps> ; set default warmup step count, 1..80
//   WARMUP_CYCLES <n>    ; set default warmup cycle count, 0..10
//   HOLD <0|1>           ; keep coils energized after MOVE
//   CALI [steps]         ; forward then backward (default 80)
//   PAUSE                ; pause the current MOVE without losing remaining steps
//   RESUME               ; continue a paused MOVE
//   STATUS               ; report IDLE/RUNNING/PAUSED and step progress
//
// Replies:
//   READY Y-motor
//   PONG
//   OK
//   DONE <steps>
//   ERR ...

#include <Arduino.h>

const char kMotorName[] = "Y-motor";
const uint8_t kMotorPins[4] = {4, 5, 6, 7};
constexpr float kFixedMotorRpm = 0.02F;
constexpr long kHalfStepsPerOutputRev = 4096L;
constexpr unsigned long kFixedStepIntervalUs =
    (unsigned long)(60000000.0F / (kFixedMotorRpm * (float)kHalfStepsPerOutputRev) + 0.5F);
static_assert(kFixedStepIntervalUs == 732422UL, "Unexpected fixed motion interval");
const unsigned long kDefaultStepDelayMs = (kFixedStepIntervalUs + 500UL) / 1000UL;
const bool kLegacyPreloadEnabled = false;
const uint8_t kDefaultWarmupSteps = 80;
const uint8_t kDefaultWarmupCycles = 1;
const uint8_t kMaxWarmupSteps = 80;
const uint8_t kMaxWarmupCycles = 10;

// 28BYJ-48 half-step sequence
const uint8_t SEQ[8][4] = {
  {1, 0, 0, 0},
  {1, 1, 0, 0},
  {0, 1, 0, 0},
  {0, 1, 1, 0},
  {0, 0, 1, 0},
  {0, 0, 1, 1},
  {0, 0, 0, 1},
  {1, 0, 0, 1},
};

int8_t g_phaseIdx = 0;
const unsigned long g_stepDelayMs = kDefaultStepDelayMs;
unsigned long g_lastStepAtUs = 0;
bool g_hasStepped = false;
uint8_t g_warmupSteps = kDefaultWarmupSteps;
uint8_t g_warmupCycles = kDefaultWarmupCycles;
int8_t g_dirSign = 1;
bool g_holdEnabled = true;
bool g_autoWarmupEnabled = false;
bool g_warmed = false;
String g_line;
bool g_moveActive = false;
bool g_movePaused = false;
bool g_continuousActive = false;
bool g_calibrationActive = false;
bool g_calibrationReturning = false;
long g_calibrationSteps = 0;
bool g_blockingMotionAbort = false;
long g_moveRequestedSteps = 0;
long g_moveExecutedSteps = 0;
long g_moveRemainingSteps = 0;
int8_t g_moveDirection = 1;
unsigned long g_nextStepAtMs = 0;

static bool parseStepsArg(const String &arg, long &steps, bool allowNoArg) {
  String t = arg;
  t.trim();

  if (t.length() == 0) {
    return allowNoArg ? true : false;
  }
  if (allowNoArg) {
    steps = 80;
  }

  // This is deliberately a single-axis firmware. Reject a second token so
  // the Python driver's "SPEED_MS 1 700" probe does not mistake this board
  // for dual-motor firmware.
  if (t.indexOf(' ') >= 0) return false;
  steps = t.toInt();
  return true;
}

static void applyPhase(uint8_t phase) {
  phase &= 7;
  digitalWrite(kMotorPins[0], SEQ[phase][0] ? HIGH : LOW);
  digitalWrite(kMotorPins[1], SEQ[phase][1] ? HIGH : LOW);
  digitalWrite(kMotorPins[2], SEQ[phase][2] ? HIGH : LOW);
  digitalWrite(kMotorPins[3], SEQ[phase][3] ? HIGH : LOW);
}

static void releaseMotor() {
  digitalWrite(kMotorPins[0], LOW);
  digitalWrite(kMotorPins[1], LOW);
  digitalWrite(kMotorPins[2], LOW);
  digitalWrite(kMotorPins[3], LOW);
}

static bool applyStep(int8_t dir) {
  // Gate at the phase-output layer, across RUN/MOVE/CALI, STOP, RESUME and
  // back-to-back one-step commands. A new command cannot reset this clock.
  unsigned long now = micros();
  if (g_hasStepped && (unsigned long)(now - g_lastStepAtUs) < kFixedStepIntervalUs) return false;
  g_lastStepAtUs = now;
  g_hasStepped = true;
  int16_t nextPhase = (int16_t)g_phaseIdx + dir;
  if (nextPhase < 0) nextPhase = 7;
  else if (nextPhase > 7) nextPhase = 0;
  g_phaseIdx = (int8_t)nextPhase;

  applyPhase((uint8_t)g_phaseIdx);
  return true;
}

static void stepRaw(int8_t dir) {
  while (!applyStep(dir)) {
    if (pollBlockingEmergencyStop()) return;
  }
}

static bool pollBlockingEmergencyStop() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c != '\n') {
      g_line += c;
      if (g_line.length() > 96) g_line = "";
      continue;
    }

    String emergencyCommand = g_line;
    g_line = "";
    emergencyCommand.trim();
    bool releaseRequested = emergencyCommand.equalsIgnoreCase(F("RELEASE"));
    if (emergencyCommand.equalsIgnoreCase(F("STOP")) || releaseRequested) {
      g_blockingMotionAbort = true;
      if (releaseRequested) {
        releaseMotor();
        Serial.println(F("OK RELEASED"));
      } else {
        Serial.println(F("OK STOPPED"));
      }
      return true;
    }
    if (emergencyCommand.length() > 0) {
      Serial.println(F("ERR BUSY; only STOP or RELEASE is accepted"));
    }
  }
  return g_blockingMotionAbort;
}

static void moveRaw(long steps) {
  if (steps == 0) return;

  long n = steps;
  if (n < 0) n = -n;
  int8_t dir = (steps > 0) ? 1 : -1;
  dir *= g_dirSign;

  for (long i = 0; i < n; i++) {
    if (pollBlockingEmergencyStop()) break;
    stepRaw(dir);
  }
}

static void runWarmup(uint8_t steps, uint8_t cycles) {
  // Retain legacy implementation for reference, but isolate it from production.
  if (!kLegacyPreloadEnabled) return;
  g_blockingMotionAbort = false;
  if (steps < 1) steps = 1;
  if (steps > kMaxWarmupSteps) steps = kMaxWarmupSteps;
  if (cycles > kMaxWarmupCycles) cycles = kMaxWarmupCycles;
  if (cycles == 0) {
    g_warmed = true;
    return;
  }


  for (uint8_t i = 0; i < cycles; i++) {
    moveRaw(steps);
    if (g_blockingMotionAbort) break;
    delay(20);
    moveRaw(-steps);
    if (g_blockingMotionAbort) break;
    delay(20);
  }

  if (!g_holdEnabled && !g_blockingMotionAbort) {
    releaseMotor();
  }
  g_warmed = !g_blockingMotionAbort;
}

static void finishActiveMove() {
  long completedSteps = g_moveRequestedSteps;
  g_moveActive = false;
  g_movePaused = false;
  g_moveRemainingSteps = 0;

  if (g_calibrationActive) {
    if (!g_calibrationReturning) {
      g_calibrationReturning = true;
      g_moveRequestedSteps = -g_calibrationSteps;
      g_moveExecutedSteps = 0;
      g_moveRemainingSteps = g_calibrationSteps;
      g_moveDirection = -1 * g_dirSign;
      g_moveActive = true;
      g_nextStepAtMs = millis();
      return;
    }
    g_calibrationActive = false;
    g_calibrationReturning = false;
    if (!g_holdEnabled) releaseMotor();
    Serial.println(F("OK CALIBRATED"));
    return;
  }

  if (!g_holdEnabled) {
    releaseMotor();
  }
  Serial.print(F("DONE "));
  Serial.println(completedSteps);
}

static void serviceActiveMove() {
  if ((!g_moveActive && !g_continuousActive) || g_movePaused) return;
  unsigned long now = millis();
  if ((long)(now - g_nextStepAtMs) < 0) return;

  if (g_continuousActive) {
    if (!applyStep(g_moveDirection)) return;
    g_moveExecutedSteps++;
    g_nextStepAtMs = now + g_stepDelayMs;
    return;
  }

  if (!applyStep(g_moveDirection)) return;
  g_moveExecutedSteps++;
  g_moveRemainingSteps--;
  if (g_moveRemainingSteps <= 0) {
    finishActiveMove();
    return;
  }
  g_nextStepAtMs = now + g_stepDelayMs;
}

static void moveSteps(long steps) {
  if (steps == 0) {
    Serial.println(F("DONE 0"));
    return;
  }
  if (g_moveActive || g_continuousActive || g_calibrationActive) {
    Serial.println(F("ERR BUSY"));
    return;
  }

  g_blockingMotionAbort = false;
  if (kLegacyPreloadEnabled && g_autoWarmupEnabled && !g_warmed) {
    runWarmup(g_warmupSteps, g_warmupCycles);
    if (g_blockingMotionAbort) return;
  }

  g_moveRequestedSteps = steps;
  g_moveExecutedSteps = 0;
  g_moveRemainingSteps = (steps < 0) ? -steps : steps;
  g_moveDirection = (steps > 0) ? 1 : -1;
  g_moveDirection *= g_dirSign;
  g_movePaused = false;
  g_moveActive = true;
  g_nextStepAtMs = millis();
}

static void handleMove(const String &arg) {
  long steps = 0;
  if (!parseStepsArg(arg, steps, false)) {
    Serial.println(F("ERR MOVE format"));
    return;
  }
  moveSteps(steps);
}

static void handleSpeed(const String &arg) {
  long ms = kDefaultStepDelayMs;
  if (!parseStepsArg(arg, ms, false)) {
    Serial.println(F("ERR SPEED_MS format"));
    return;
  }
  if (ms != (long)kDefaultStepDelayMs) {
    Serial.println(F("ERR FIXED_RPM 0.020"));
    return;
  }
  Serial.println(F("OK"));
}

static bool isFixedRpm(const String &text) {
  char *end = NULL;
  const char *start = text.c_str();
  double rpm = strtod(start, &end);
  return end != start && *end == '\0' && fabs(rpm - kFixedMotorRpm) < 0.00000001;
}

static void handleSpeedRpm(const String &arg) {
  String t = arg;
  t.trim();
  if (t.length() == 0 || t.indexOf(' ') >= 0) {
    Serial.println(F("ERR SPEED_RPM format"));
    return;
  }
  if (!isFixedRpm(t)) {
    Serial.println(F("ERR FIXED_RPM 0.020"));
    return;
  }
  Serial.println(F("OK"));
}

static void handleRun(const String &arg) {
  if (g_calibrationActive || g_moveActive) {
    Serial.println(F("ERR BUSY"));
    return;
  }

  String t = arg;
  t.trim();
  int sp = t.indexOf(' ');
  String direction = sp < 0 ? t : t.substring(0, sp);
  String rpmText = sp < 0 ? "" : t.substring(sp + 1);
  direction.trim();
  rpmText.trim();
  if (rpmText.length() > 0 && !isFixedRpm(rpmText)) {
    Serial.println(F("ERR FIXED_RPM 0.020"));
    return;
  }

  if (direction.equalsIgnoreCase(F("CW"))) {
    g_moveDirection = 1 * g_dirSign;
  } else if (direction.equalsIgnoreCase(F("CCW"))) {
    g_moveDirection = -1 * g_dirSign;
  } else {
    Serial.println(F("ERR RUN direction must be CW or CCW"));
    return;
  }

  g_moveRequestedSteps = 0;
  g_moveExecutedSteps = 0;
  g_moveRemainingSteps = -1;
  g_movePaused = false;
  g_continuousActive = true;
  g_nextStepAtMs = millis();
  Serial.println(F("OK RUNNING"));
}

static void handleDir(const String &arg) {
  String t = arg;
  t.trim();
  if (t.length() == 0) {
    Serial.println(F("ERR DIR format"));
    return;
  }

  int sp = t.indexOf(' ');
  if (sp >= 0) {
    String first = t.substring(0, sp);
    String second = t.substring(sp + 1);
    first.trim();
    second.trim();
    if ((first == "0" || first == "1") && second.length() > 0) {
      t = second;
    } else {
      Serial.println(F("ERR DIR format"));
      return;
    }
  }

  int sign = t.toInt();
  g_dirSign = (sign >= 0) ? 1 : -1;
  g_warmed = false;
  Serial.println(F("OK"));
}

static void handleWarmup(const String &arg) {
  if (!kLegacyPreloadEnabled) {
    Serial.println(F("ERR PRELOAD_DISABLED"));
    return;
  }
  String t = arg;
  t.trim();
  int firstSp = t.indexOf(' ');
  if (firstSp >= 0) {
    String first = t.substring(0, firstSp);
    String rest = t.substring(firstSp + 1);
    first.trim();
    rest.trim();
    if ((first == "0" || first == "1") && rest.length() > 0) {
      t = rest;
    }
  }
  long steps = g_warmupSteps;
  long cycles = g_warmupCycles;

  if (t.length() > 0) {
    int sp = t.indexOf(' ');
    if (sp < 0) {
      steps = t.toInt();
    } else {
      String first = t.substring(0, sp);
      String second = t.substring(sp + 1);
      first.trim();
      second.trim();
      steps = first.toInt();
      if (second.length() > 0) {
        cycles = second.toInt();
      }
    }
  }

  if (steps < 1) steps = 1;
  if (steps > kMaxWarmupSteps) steps = kMaxWarmupSteps;
  if (cycles < 0) cycles = 0;
  if (cycles > kMaxWarmupCycles) cycles = kMaxWarmupCycles;

  Serial.print(F("WARMUP "));
  Serial.print(kMotorName);
  Serial.print(F(" steps="));
  Serial.print(steps);
  Serial.print(F(" cycles="));
  Serial.println(cycles);
  runWarmup((uint8_t)steps, (uint8_t)cycles);
  if (g_blockingMotionAbort) return;
  Serial.println(F("OK"));
}

static void handleAutoWarm(const String &arg) {
  long enabled = 1;
  if (!parseStepsArg(arg, enabled, false)) {
    Serial.println(F("ERR AUTOWARM format"));
    return;
  }
  if (!kLegacyPreloadEnabled && enabled != 0) {
    Serial.println(F("ERR PRELOAD_DISABLED"));
    return;
  }
  g_autoWarmupEnabled = (enabled != 0);
  if (!g_autoWarmupEnabled) {
    g_warmed = true;
  }
  Serial.println(F("OK"));
}

static void handleWarmupSteps(const String &arg) {
  long steps = kDefaultWarmupSteps;
  if (!parseStepsArg(arg, steps, false)) {
    Serial.println(F("ERR WARMUP_STEPS format"));
    return;
  }
  if (steps < 1) steps = 1;
  if (steps > kMaxWarmupSteps) steps = kMaxWarmupSteps;
  g_warmupSteps = (uint8_t)steps;
  g_warmed = false;
  Serial.println(F("OK"));
}

static void handleWarmupCycles(const String &arg) {
  long cycles = kDefaultWarmupCycles;
  if (!parseStepsArg(arg, cycles, false)) {
    Serial.println(F("ERR WARMUP_CYCLES format"));
    return;
  }
  if (cycles < 0) cycles = 0;
  if (cycles > kMaxWarmupCycles) cycles = kMaxWarmupCycles;
  g_warmupCycles = (uint8_t)cycles;
  g_warmed = false;
  Serial.println(F("OK"));
}

static void handleHold(const String &arg) {
  long enabled = 1;
  if (!parseStepsArg(arg, enabled, false)) {
    Serial.println(F("ERR HOLD format"));
    return;
  }
  g_holdEnabled = (enabled != 0);
  if (!g_holdEnabled) {
    releaseMotor();
  } else {
    applyPhase((uint8_t)g_phaseIdx);
  }
  Serial.println(F("OK"));
}

static void handleCali(const String &arg) {
  if (g_moveActive || g_continuousActive || g_calibrationActive) {
    Serial.println(F("ERR BUSY"));
    return;
  }
  long steps = 80;
  if (!parseStepsArg(arg, steps, true)) {
    Serial.println(F("ERR CALI format"));
    return;
  }

  if (steps <= 0) steps = 80;
  if (steps > 20000) steps = 20000;

  g_blockingMotionAbort = false;

  Serial.print(F("CALI "));
  Serial.print(F("Y-motor "));
  Serial.println(steps);

  // Non-blocking forward/return calibration. serviceActiveMove() advances it,
  // so STOP remains responsive throughout the whole calibration.
  g_calibrationActive = true;
  g_calibrationReturning = false;
  g_calibrationSteps = steps;
  g_moveRequestedSteps = steps;
  g_moveExecutedSteps = 0;
  g_moveRemainingSteps = steps;
  g_moveDirection = 1 * g_dirSign;
  g_movePaused = false;
  g_moveActive = true;
  g_nextStepAtMs = millis();
}

static void handlePause() {
  if (g_moveActive || g_continuousActive) {
    g_movePaused = true;
    Serial.println(F("OK PAUSED"));
  } else {
    Serial.println(F("OK IDLE"));
  }
}

static void handleResume() {
  if ((g_moveActive || g_continuousActive) && g_movePaused) {
    g_movePaused = false;
    g_nextStepAtMs = millis();
    Serial.println(F("OK RUNNING"));
  } else if (g_moveActive || g_continuousActive) {
    Serial.println(F("OK RUNNING"));
  } else {
    Serial.println(F("OK IDLE"));
  }
}

static void handleStatus() {
  Serial.print(F("STATUS "));
  if (!g_moveActive && !g_continuousActive) {
    Serial.print(F("IDLE "));
  } else if (g_movePaused) {
    Serial.print(F("PAUSED "));
  } else {
    Serial.print(F("RUNNING "));
  }
  Serial.print(g_moveRequestedSteps);
  Serial.print(F(" "));
  Serial.print(g_moveExecutedSteps);
  Serial.print(F(" "));
  Serial.println(g_moveRemainingSteps);
}

static void handleStop(bool releaseCoils) {
  g_moveActive = false;
  g_continuousActive = false;
  g_movePaused = false;
  g_moveRemainingSteps = 0;
  g_calibrationActive = false;
  g_calibrationReturning = false;
  g_blockingMotionAbort = true;
  if (releaseCoils) {
    releaseMotor();
  }
  g_warmed = false;
  if (releaseCoils) {
    Serial.println(F("OK RELEASED"));
  } else {
    Serial.println(F("OK STOPPED"));
  }
}

static void handleCommand(const String &line) {
  String cmd = line;
  cmd.trim();
  if (cmd.length() == 0) return;
  if (cmd.equalsIgnoreCase(F("FIRMWARE_ID"))) {
    Serial.println(F("FIRMWARE_ID MSH_FIXED_002RPM_V1 AXIS=Y BOARD=MSH-B-Y-01 BUILD=20260916-01 TOPOLOGY=DUAL_UNO"));
    return;
  }
  if (cmd.equalsIgnoreCase(F("MOTION_POLICY"))) {
    Serial.print(F("MOTION_POLICY RPM=0.020 STEPS_PER_REV=4096 STEP_US="));
    Serial.print(kFixedStepIntervalUs);
    Serial.println(F(" PRELOAD=OFF"));
    return;
  }

  if (cmd.equalsIgnoreCase(F("PING"))) {
    Serial.println(F("PONG"));
    return;
  }
  if (cmd.startsWith(F("MOVE"))) {
    int sp = cmd.indexOf(' ');
    if (sp < 0) {
      Serial.println(F("ERR MOVE requires argument"));
      return;
    }
    handleMove(cmd.substring(sp + 1));
    return;
  }
  if (cmd.startsWith(F("SPEED_MS"))) {
    int sp = cmd.indexOf(' ');
    if (sp < 0) {
      Serial.println(F("ERR SPEED_MS requires argument"));
      return;
    }
    handleSpeed(cmd.substring(sp + 1));
    return;
  }
  if (cmd.startsWith(F("SPEED_RPM"))) {
    int sp = cmd.indexOf(' ');
    if (sp < 0) {
      Serial.println(F("ERR SPEED_RPM requires argument"));
      return;
    }
    handleSpeedRpm(cmd.substring(sp + 1));
    return;
  }
  if (cmd.startsWith(F("RUN"))) {
    int sp = cmd.indexOf(' ');
    if (sp < 0) {
      Serial.println(F("ERR RUN requires direction"));
      return;
    }
    handleRun(cmd.substring(sp + 1));
    return;
  }
  if (cmd.startsWith(F("DIR"))) {
    int sp = cmd.indexOf(' ');
    if (sp < 0) {
      Serial.println(F("ERR DIR requires argument"));
      return;
    }
    handleDir(cmd.substring(sp + 1));
    return;
  }
  if (cmd.startsWith(F("WARMUP_STEPS"))) {
    int sp = cmd.indexOf(' ');
    if (sp < 0) {
      Serial.println(F("ERR WARMUP_STEPS requires argument"));
      return;
    }
    handleWarmupSteps(cmd.substring(sp + 1));
    return;
  }
  if (cmd.startsWith(F("WARMUP_CYCLES"))) {
    int sp = cmd.indexOf(' ');
    if (sp < 0) {
      Serial.println(F("ERR WARMUP_CYCLES requires argument"));
      return;
    }
    handleWarmupCycles(cmd.substring(sp + 1));
    return;
  }
  if (cmd.startsWith(F("AUTOWARM"))) {
    int sp = cmd.indexOf(' ');
    if (sp < 0) {
      Serial.println(F("ERR AUTOWARM requires argument"));
      return;
    }
    handleAutoWarm(cmd.substring(sp + 1));
    return;
  }
  if (cmd.startsWith(F("WARMUP"))) {
    int sp = cmd.indexOf(' ');
    if (sp < 0) {
      handleWarmup("");
      return;
    }
    handleWarmup(cmd.substring(sp + 1));
    return;
  }
  if (cmd.startsWith(F("HOLD"))) {
    int sp = cmd.indexOf(' ');
    if (sp < 0) {
      handleHold("1");
      return;
    }
    handleHold(cmd.substring(sp + 1));
    return;
  }
  if (cmd.startsWith(F("CALI"))) {
    int sp = cmd.indexOf(' ');
    if (sp < 0) {
      handleCali("");
      return;
    }
    handleCali(cmd.substring(sp + 1));
    return;
  }
  if (cmd.equalsIgnoreCase(F("PAUSE"))) {
    handlePause();
    return;
  }
  if (cmd.equalsIgnoreCase(F("RESUME"))) {
    handleResume();
    return;
  }
  if (cmd.equalsIgnoreCase(F("STATUS"))) {
    handleStatus();
    return;
  }
  if (cmd.equalsIgnoreCase(F("STOP"))) {
    handleStop(false);
    return;
  }
  if (cmd.equalsIgnoreCase(F("RELEASE"))) {
    handleStop(true);
    return;
  }
  Serial.println(F("ERR unknown"));
}

void setup() {
  for (uint8_t i = 0; i < 4; i++) {
    pinMode(kMotorPins[i], OUTPUT);
  }
  releaseMotor();
  g_phaseIdx = 0;
  g_warmupSteps = kDefaultWarmupSteps;
  g_warmupCycles = kDefaultWarmupCycles;
  g_dirSign = 1;
  g_holdEnabled = true;
  g_autoWarmupEnabled = false;
  g_warmed = false;

  Serial.begin(115200);
  delay(300);
  Serial.print(F("READY "));
  Serial.println(kMotorName);
}

void loop() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n') {
      handleCommand(g_line);
      g_line = "";
    } else if (c != '\r') {
      g_line += c;
      if (g_line.length() > 96) {
        g_line = "";
      }
    }
  }
  serviceActiveMove();
}
