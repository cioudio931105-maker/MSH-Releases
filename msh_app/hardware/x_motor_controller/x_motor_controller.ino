// Arduino 28BYJ-48 + ULN2003 Serial Controller for X-motor
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
//   SPEED_MS <ms>        ; 1..250 (ms per half-step)
//   DIR <-1|1>           ; set direction sign
//   WARMUP [steps] [cycles] ; small forward/backward preload, default 80 steps x 3 cycles
//   AUTOWARM <0|1>       ; auto warmup before the first MOVE after boot/STOP
//   WARMUP_STEPS <steps> ; set default warmup step count, 1..80
//   WARMUP_CYCLES <n>    ; set default warmup cycle count, 0..10
//   HOLD <0|1>           ; keep coils energized after MOVE
//   CALI [steps]         ; forward then backward (default 80)
//   PAUSE                ; pause the current MOVE without losing remaining steps
//   RESUME               ; continue a paused MOVE
//   STATUS               ; report IDLE/RUNNING/PAUSED and step progress
//   STOP                 ; release motor
//
// Replies:
//   READY X-motor
//   PONG
//   OK
//   DONE <steps>
//   ERR ...

#include <Arduino.h>

const char kMotorName[] = "X-motor";
const uint8_t kMotorPins[4] = {4, 5, 6, 7};
const uint8_t kDefaultStepDelayMs = 5;
const uint8_t kMinStepDelayMs = 1;
const uint8_t kMaxStepDelayMs = 250;
const uint8_t kDefaultWarmupSteps = 80;
const uint8_t kDefaultWarmupCycles = 1;
const uint8_t kMaxWarmupSteps = 80;
const uint8_t kMaxWarmupCycles = 10;
const uint8_t kWarmupMinDelayMs = 8;

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
uint8_t g_stepDelayMs = kDefaultStepDelayMs;
uint8_t g_warmupSteps = kDefaultWarmupSteps;
uint8_t g_warmupCycles = kDefaultWarmupCycles;
int8_t g_dirSign = 1;
bool g_holdEnabled = true;
bool g_autoWarmupEnabled = true;
bool g_warmed = false;
String g_line;
bool g_moveActive = false;
bool g_movePaused = false;
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

  int sp = t.indexOf(' ');
  if (sp < 0) {
    steps = t.toInt();
    return true;
  }

  String first = t.substring(0, sp);
  String second = t.substring(sp + 1);
  first.trim();
  second.trim();

  if ((first == "0" || first == "1") && second.length() > 0) {
    steps = second.toInt();
    return true;
  }

  return false;
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

static void applyStep(int8_t dir) {
  int16_t nextPhase = (int16_t)g_phaseIdx + dir;
  if (nextPhase < 0) nextPhase = 7;
  else if (nextPhase > 7) nextPhase = 0;
  g_phaseIdx = (int8_t)nextPhase;

  applyPhase((uint8_t)g_phaseIdx);
}

static void stepRaw(int8_t dir) {
  applyStep(dir);
  delay(g_stepDelayMs);
}

static void moveRaw(long steps) {
  if (steps == 0) return;

  long n = steps;
  if (n < 0) n = -n;
  int8_t dir = (steps > 0) ? 1 : -1;
  dir *= g_dirSign;

  for (long i = 0; i < n; i++) {
    stepRaw(dir);
  }
}

static void runWarmup(uint8_t steps, uint8_t cycles) {
  if (steps < 1) steps = 1;
  if (steps > kMaxWarmupSteps) steps = kMaxWarmupSteps;
  if (cycles > kMaxWarmupCycles) cycles = kMaxWarmupCycles;
  if (cycles == 0) {
    g_warmed = true;
    return;
  }

  uint8_t prevDelay = g_stepDelayMs;
  if (g_stepDelayMs < kWarmupMinDelayMs) {
    g_stepDelayMs = kWarmupMinDelayMs;
  }

  for (uint8_t i = 0; i < cycles; i++) {
    moveRaw(steps);
    delay(20);
    moveRaw(-steps);
    delay(20);
  }

  g_stepDelayMs = prevDelay;
  if (!g_holdEnabled) {
    releaseMotor();
  }
  g_warmed = true;
}

static void finishActiveMove() {
  long completedSteps = g_moveRequestedSteps;
  g_moveActive = false;
  g_movePaused = false;
  g_moveRemainingSteps = 0;
  if (!g_holdEnabled) {
    releaseMotor();
  }
  Serial.print(F("DONE "));
  Serial.println(completedSteps);
}

static void serviceActiveMove() {
  if (!g_moveActive || g_movePaused) return;
  unsigned long now = millis();
  if ((long)(now - g_nextStepAtMs) < 0) return;

  applyStep(g_moveDirection);
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
  if (g_moveActive) {
    Serial.println(F("ERR BUSY"));
    return;
  }

  if (g_autoWarmupEnabled && !g_warmed) {
    runWarmup(g_warmupSteps, g_warmupCycles);
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
  if (ms < kMinStepDelayMs) ms = kMinStepDelayMs;
  if (ms > kMaxStepDelayMs) ms = kMaxStepDelayMs;
  g_stepDelayMs = (uint8_t)ms;
  Serial.println(F("OK"));
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
  Serial.println(F("OK"));
}

static void handleAutoWarm(const String &arg) {
  long enabled = 1;
  if (!parseStepsArg(arg, enabled, false)) {
    Serial.println(F("ERR AUTOWARM format"));
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
  if (g_moveActive) {
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

  uint8_t prevDelay = g_stepDelayMs;
  if (g_stepDelayMs < 12) g_stepDelayMs = 12;

  Serial.print(F("CALI "));
  Serial.print(F("X-motor "));
  Serial.println(steps);

  moveRaw(steps);
  moveRaw(-steps);
  if (!g_holdEnabled) {
    releaseMotor();
  }
  g_stepDelayMs = prevDelay;
  Serial.println(F("OK"));
}

static void handlePause() {
  if (g_moveActive) {
    g_movePaused = true;
    Serial.println(F("OK PAUSED"));
  } else {
    Serial.println(F("OK IDLE"));
  }
}

static void handleResume() {
  if (g_moveActive && g_movePaused) {
    g_movePaused = false;
    g_nextStepAtMs = millis();
    Serial.println(F("OK RUNNING"));
  } else if (g_moveActive) {
    Serial.println(F("OK RUNNING"));
  } else {
    Serial.println(F("OK IDLE"));
  }
}

static void handleStatus() {
  Serial.print(F("STATUS "));
  if (!g_moveActive) {
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

static void handleStop() {
  g_moveActive = false;
  g_movePaused = false;
  g_moveRemainingSteps = 0;
  releaseMotor();
  g_warmed = false;
  Serial.println(F("OK STOPPED"));
}

static void handleCommand(const String &line) {
  String cmd = line;
  cmd.trim();
  if (cmd.length() == 0) return;

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
    handleStop();
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
  g_stepDelayMs = kDefaultStepDelayMs;
  g_warmupSteps = kDefaultWarmupSteps;
  g_warmupCycles = kDefaultWarmupCycles;
  g_dirSign = 1;
  g_holdEnabled = true;
  g_autoWarmupEnabled = true;
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
