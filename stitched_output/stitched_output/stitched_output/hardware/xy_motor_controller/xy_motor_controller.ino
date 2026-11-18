// 28BYJ-48 + ULN2003 XY serial controller
// ------------------------------------------------------------
// 目的：
//   將原本 X / Y 兩份單軸 Arduino 程式合併成同一片 Arduino 控制兩個馬達。
//   motor 0 = X 軸，motor 1 = Y 軸。
//
// 接線：
//   X 軸 ULN2003：IN1 -> D4,  IN2 -> D5,  IN3 -> D6,  IN4 -> D7
//   Y 軸 ULN2003：IN1 -> D8,  IN2 -> D9,  IN3 -> D10, IN4 -> D11
//
// Serial 設定：
//   Baud rate = 115200
//   每個指令以 newline 結尾。
//
// 支援指令：
//   PING
//   MOVE <steps>                 // 舊格式：控制 X 軸
//   MOVE <motor> <steps>         // motor 0=X, 1=Y；steps 可正可負
//   SPEED_MS <ms>                // 舊格式：設定 X 軸 half-step 間隔
//   SPEED_MS <motor> <ms>        // ms 範圍 1..250
//   DIR <sign>                   // 舊格式：設定 X 軸方向，sign 為 1 或 -1
//   DIR <motor> <sign>
//   WARMUP [steps] [cycles]      // 舊格式：X 軸暖機
//   WARMUP <motor> <steps> <cycles>
//   AUTOWARM <0|1>               // 舊格式：X 軸是否第一次 MOVE 前自動暖機
//   AUTOWARM <motor> <0|1>
//   WARMUP_STEPS <steps>         // 舊格式：X 軸預設暖機步數
//   WARMUP_STEPS <motor> <steps>
//   WARMUP_CYCLES <cycles>       // 舊格式：X 軸預設暖機次數
//   WARMUP_CYCLES <motor> <cycles>
//   HOLD <0|1>                   // 舊格式：X 軸移動後是否保持通電
//   HOLD <motor> <0|1>
//   CALI [steps]                 // 舊格式：X 軸正反向校正測試
//   CALI <motor> <steps>
//   PAUSE [motor]
//   RESUME [motor]
//   STATUS [motor]
//   STOP [motor]                 // 無 motor 時停止並釋放 X/Y 兩軸
//
// 回覆：
//   READY XY
//   PONG
//   OK / OK ...
//   DONE <signed_steps>
//   STATUS <IDLE|RUNNING|PAUSED> <requested_steps> <executed_steps> <remaining_steps>
//   ERR ...

#include <Arduino.h>

const uint8_t MOTOR_COUNT = 2;
const uint8_t MOTOR_PIN_COUNT = 4;

const char *MOTOR_NAME[MOTOR_COUNT] = {"X", "Y"};

// motor 0 = X, motor 1 = Y
const uint8_t MOTOR_PIN[MOTOR_COUNT][MOTOR_PIN_COUNT] = {
  {4, 5, 6, 7},
  {8, 9, 10, 11},
};

// 28BYJ-48 half-step sequence. 8 相比 full-step 更適合顯微鏡載台微小移動。
const uint8_t HALF_STEP_SEQ[8][4] = {
  {1, 0, 0, 0},
  {1, 1, 0, 0},
  {0, 1, 0, 0},
  {0, 1, 1, 0},
  {0, 0, 1, 0},
  {0, 0, 1, 1},
  {0, 0, 0, 1},
  {1, 0, 0, 1},
};

const uint8_t DEFAULT_STEP_DELAY_MS = 5;
const uint8_t MIN_STEP_DELAY_MS = 1;
const uint8_t MAX_STEP_DELAY_MS = 250;
const uint8_t DEFAULT_WARMUP_STEPS = 80;
const uint8_t DEFAULT_WARMUP_CYCLES = 1;
const uint8_t MAX_WARMUP_STEPS = 80;
const uint8_t MAX_WARMUP_CYCLES = 10;
const uint8_t WARMUP_MIN_DELAY_MS = 8;

int8_t g_phaseIdx[MOTOR_COUNT] = {0, 0};
uint8_t g_stepDelayMs[MOTOR_COUNT] = {DEFAULT_STEP_DELAY_MS, DEFAULT_STEP_DELAY_MS};
uint8_t g_warmupSteps[MOTOR_COUNT] = {DEFAULT_WARMUP_STEPS, DEFAULT_WARMUP_STEPS};
uint8_t g_warmupCycles[MOTOR_COUNT] = {DEFAULT_WARMUP_CYCLES, DEFAULT_WARMUP_CYCLES};
int8_t g_dirSign[MOTOR_COUNT] = {1, 1};
bool g_holdEnabled[MOTOR_COUNT] = {true, true};
bool g_autoWarmupEnabled[MOTOR_COUNT] = {true, true};
bool g_warmed[MOTOR_COUNT] = {false, false};

bool g_moveActive[MOTOR_COUNT] = {false, false};
bool g_movePaused[MOTOR_COUNT] = {false, false};
long g_moveRequestedSteps[MOTOR_COUNT] = {0, 0};
long g_moveExecutedSteps[MOTOR_COUNT] = {0, 0};
long g_moveRemainingSteps[MOTOR_COUNT] = {0, 0};
int8_t g_moveDirection[MOTOR_COUNT] = {1, 1};
unsigned long g_nextStepAtMs[MOTOR_COUNT] = {0, 0};

String g_line;

static int parseMotorIndex(String text) {
  text.trim();
  if (text.length() != 1) {
    return -1;
  }
  char c = text.charAt(0);
  if (c != '0' && c != '1') {
    return -1;
  }
  return c - '0';
}

// 解析「<value>」或「<motor> <value>」格式。
// allowBareValue=true 時，單一數字會被視為 motor 0 的 value，以保留舊版單軸指令相容性。
static bool parseMotorValue(
  const String &arg,
  int &motorIdx,
  long &value,
  bool allowBareValue,
  bool allowMissingValue,
  long defaultValue
) {
  String text = arg;
  text.trim();

  if (text.length() == 0) {
    if (!allowMissingValue) {
      return false;
    }
    motorIdx = 0;
    value = defaultValue;
    return true;
  }

  int sp = text.indexOf(' ');
  if (sp < 0) {
    if (allowBareValue) {
      motorIdx = 0;
      value = text.toInt();
      return true;
    }
    int maybeMotor = parseMotorIndex(text);
    if (allowMissingValue && maybeMotor >= 0) {
      motorIdx = maybeMotor;
      value = defaultValue;
      return true;
    }
    return false;
  }

  String first = text.substring(0, sp);
  String rest = text.substring(sp + 1);
  first.trim();
  rest.trim();

  int parsedMotor = parseMotorIndex(first);
  if (parsedMotor < 0) {
    return false;
  }

  motorIdx = parsedMotor;
  if (rest.length() == 0) {
    if (!allowMissingValue) {
      return false;
    }
    value = defaultValue;
    return true;
  }

  value = rest.toInt();
  return true;
}

static bool parseOptionalMotor(const String &arg, int &motorIdx, bool &hasMotor) {
  String text = arg;
  text.trim();
  if (text.length() == 0) {
    motorIdx = 0;
    hasMotor = false;
    return true;
  }

  int parsedMotor = parseMotorIndex(text);
  if (parsedMotor < 0) {
    return false;
  }

  motorIdx = parsedMotor;
  hasMotor = true;
  return true;
}

static bool validateMotor(int motorIdx) {
  if (motorIdx < 0 || motorIdx >= MOTOR_COUNT) {
    Serial.println(F("ERR invalid motor"));
    return false;
  }
  return true;
}

static void applyPhase(uint8_t motorIdx, uint8_t phase) {
  phase &= 7;
  for (uint8_t pinIdx = 0; pinIdx < MOTOR_PIN_COUNT; pinIdx++) {
    digitalWrite(
      MOTOR_PIN[motorIdx][pinIdx],
      HALF_STEP_SEQ[phase][pinIdx] ? HIGH : LOW
    );
  }
}

static void releaseMotor(uint8_t motorIdx) {
  for (uint8_t pinIdx = 0; pinIdx < MOTOR_PIN_COUNT; pinIdx++) {
    digitalWrite(MOTOR_PIN[motorIdx][pinIdx], LOW);
  }
}

static void releaseAllMotors() {
  for (uint8_t motorIdx = 0; motorIdx < MOTOR_COUNT; motorIdx++) {
    releaseMotor(motorIdx);
  }
}

static void applyStep(uint8_t motorIdx, int8_t dir) {
  int16_t nextPhase = (int16_t)g_phaseIdx[motorIdx] + dir;
  if (nextPhase < 0) {
    nextPhase = 7;
  } else if (nextPhase > 7) {
    nextPhase = 0;
  }
  g_phaseIdx[motorIdx] = (int8_t)nextPhase;
  applyPhase(motorIdx, (uint8_t)g_phaseIdx[motorIdx]);
}

static void stepRaw(uint8_t motorIdx, int8_t dir) {
  applyStep(motorIdx, dir);
  delay(g_stepDelayMs[motorIdx]);
}

static void moveRaw(uint8_t motorIdx, long steps) {
  if (steps == 0) {
    return;
  }

  long count = steps;
  if (count < 0) {
    count = -count;
  }

  int8_t dir = (steps > 0) ? 1 : -1;
  dir *= g_dirSign[motorIdx];

  for (long i = 0; i < count; i++) {
    stepRaw(motorIdx, dir);
  }
}

static bool anyMotorActive() {
  for (uint8_t motorIdx = 0; motorIdx < MOTOR_COUNT; motorIdx++) {
    if (g_moveActive[motorIdx]) {
      return true;
    }
  }
  return false;
}

static void runWarmup(uint8_t motorIdx, uint8_t steps, uint8_t cycles) {
  if (steps < 1) {
    steps = 1;
  }
  if (steps > MAX_WARMUP_STEPS) {
    steps = MAX_WARMUP_STEPS;
  }
  if (cycles > MAX_WARMUP_CYCLES) {
    cycles = MAX_WARMUP_CYCLES;
  }
  if (cycles == 0) {
    g_warmed[motorIdx] = true;
    return;
  }

  uint8_t previousDelay = g_stepDelayMs[motorIdx];
  if (g_stepDelayMs[motorIdx] < WARMUP_MIN_DELAY_MS) {
    g_stepDelayMs[motorIdx] = WARMUP_MIN_DELAY_MS;
  }

  for (uint8_t cycle = 0; cycle < cycles; cycle++) {
    moveRaw(motorIdx, steps);
    delay(20);
    moveRaw(motorIdx, -steps);
    delay(20);
  }

  g_stepDelayMs[motorIdx] = previousDelay;
  if (!g_holdEnabled[motorIdx]) {
    releaseMotor(motorIdx);
  }
  g_warmed[motorIdx] = true;
}

static void finishActiveMove(uint8_t motorIdx) {
  long completed = g_moveRequestedSteps[motorIdx];
  g_moveActive[motorIdx] = false;
  g_movePaused[motorIdx] = false;
  g_moveRemainingSteps[motorIdx] = 0;
  if (!g_holdEnabled[motorIdx]) {
    releaseMotor(motorIdx);
  }

  Serial.print(F("DONE "));
  Serial.println(completed);
}

static void serviceMotor(uint8_t motorIdx) {
  if (!g_moveActive[motorIdx] || g_movePaused[motorIdx]) {
    return;
  }

  unsigned long now = millis();
  if ((long)(now - g_nextStepAtMs[motorIdx]) < 0) {
    return;
  }

  applyStep(motorIdx, g_moveDirection[motorIdx]);
  g_moveExecutedSteps[motorIdx]++;
  g_moveRemainingSteps[motorIdx]--;

  if (g_moveRemainingSteps[motorIdx] <= 0) {
    finishActiveMove(motorIdx);
    return;
  }

  g_nextStepAtMs[motorIdx] = now + g_stepDelayMs[motorIdx];
}

static void serviceAllMotors() {
  for (uint8_t motorIdx = 0; motorIdx < MOTOR_COUNT; motorIdx++) {
    serviceMotor(motorIdx);
  }
}

static void startMove(uint8_t motorIdx, long steps) {
  if (steps == 0) {
    Serial.println(F("DONE 0"));
    return;
  }
  if (g_moveActive[motorIdx]) {
    Serial.println(F("ERR BUSY"));
    return;
  }

  if (g_autoWarmupEnabled[motorIdx] && !g_warmed[motorIdx]) {
    runWarmup(motorIdx, g_warmupSteps[motorIdx], g_warmupCycles[motorIdx]);
  }

  g_moveRequestedSteps[motorIdx] = steps;
  g_moveExecutedSteps[motorIdx] = 0;
  g_moveRemainingSteps[motorIdx] = (steps < 0) ? -steps : steps;
  g_moveDirection[motorIdx] = (steps > 0) ? 1 : -1;
  g_moveDirection[motorIdx] *= g_dirSign[motorIdx];
  g_movePaused[motorIdx] = false;
  g_moveActive[motorIdx] = true;
  g_nextStepAtMs[motorIdx] = millis();
}

static void handleMove(const String &arg) {
  int motor = 0;
  long steps = 0;
  if (!parseMotorValue(arg, motor, steps, true, false, 0)) {
    Serial.println(F("ERR MOVE format"));
    return;
  }
  if (!validateMotor(motor)) {
    return;
  }
  startMove((uint8_t)motor, steps);
}

static void handleSpeed(const String &arg) {
  int motor = 0;
  long ms = DEFAULT_STEP_DELAY_MS;
  if (!parseMotorValue(arg, motor, ms, true, false, DEFAULT_STEP_DELAY_MS)) {
    Serial.println(F("ERR SPEED_MS format"));
    return;
  }
  if (!validateMotor(motor)) {
    return;
  }

  if (ms < MIN_STEP_DELAY_MS) {
    ms = MIN_STEP_DELAY_MS;
  }
  if (ms > MAX_STEP_DELAY_MS) {
    ms = MAX_STEP_DELAY_MS;
  }

  g_stepDelayMs[motor] = (uint8_t)ms;
  Serial.println(F("OK"));
}

static void handleDir(const String &arg) {
  int motor = 0;
  long sign = 1;
  if (!parseMotorValue(arg, motor, sign, true, false, 1)) {
    Serial.println(F("ERR DIR format"));
    return;
  }
  if (!validateMotor(motor)) {
    return;
  }

  g_dirSign[motor] = (sign >= 0) ? 1 : -1;
  g_warmed[motor] = false;
  Serial.println(F("OK"));
}

static void handleWarmup(const String &arg) {
  int motor = 0;
  long steps = DEFAULT_WARMUP_STEPS;
  long cycles = DEFAULT_WARMUP_CYCLES;
  String text = arg;
  text.trim();

  if (anyMotorActive()) {
    Serial.println(F("ERR BUSY"));
    return;
  }

  if (text.length() > 0) {
    int firstSpace = text.indexOf(' ');
    if (firstSpace < 0) {
      // WARMUP 40：舊格式，X 軸暖機 40 steps。
      steps = text.toInt();
    } else {
      String first = text.substring(0, firstSpace);
      String rest = text.substring(firstSpace + 1);
      first.trim();
      rest.trim();

      int parsedMotor = parseMotorIndex(first);
      if (parsedMotor >= 0) {
        motor = parsedMotor;
        int secondSpace = rest.indexOf(' ');
        if (secondSpace < 0) {
          steps = rest.toInt();
        } else {
          String stepText = rest.substring(0, secondSpace);
          String cycleText = rest.substring(secondSpace + 1);
          stepText.trim();
          cycleText.trim();
          steps = stepText.toInt();
          if (cycleText.length() > 0) {
            cycles = cycleText.toInt();
          }
        }
      } else {
        // WARMUP 40 2：舊格式，X 軸 40 steps x 2 cycles。
        String stepText = first;
        String cycleText = rest;
        steps = stepText.toInt();
        if (cycleText.length() > 0) {
          cycles = cycleText.toInt();
        }
      }
    }
  }

  if (!validateMotor(motor)) {
    return;
  }
  if (steps < 1) {
    steps = 1;
  }
  if (steps > MAX_WARMUP_STEPS) {
    steps = MAX_WARMUP_STEPS;
  }
  if (cycles < 0) {
    cycles = 0;
  }
  if (cycles > MAX_WARMUP_CYCLES) {
    cycles = MAX_WARMUP_CYCLES;
  }

  Serial.print(F("WARMUP "));
  Serial.print(MOTOR_NAME[motor]);
  Serial.print(F(" steps="));
  Serial.print(steps);
  Serial.print(F(" cycles="));
  Serial.println(cycles);

  runWarmup((uint8_t)motor, (uint8_t)steps, (uint8_t)cycles);
  Serial.println(F("OK"));
}

static void handleAutoWarm(const String &arg) {
  int motor = 0;
  long enabled = 1;
  if (!parseMotorValue(arg, motor, enabled, true, false, 1)) {
    Serial.println(F("ERR AUTOWARM format"));
    return;
  }
  if (!validateMotor(motor)) {
    return;
  }

  g_autoWarmupEnabled[motor] = (enabled != 0);
  if (!g_autoWarmupEnabled[motor]) {
    g_warmed[motor] = true;
  }
  Serial.println(F("OK"));
}

static void handleWarmupSteps(const String &arg) {
  int motor = 0;
  long steps = DEFAULT_WARMUP_STEPS;
  if (!parseMotorValue(arg, motor, steps, true, false, DEFAULT_WARMUP_STEPS)) {
    Serial.println(F("ERR WARMUP_STEPS format"));
    return;
  }
  if (!validateMotor(motor)) {
    return;
  }

  if (steps < 1) {
    steps = 1;
  }
  if (steps > MAX_WARMUP_STEPS) {
    steps = MAX_WARMUP_STEPS;
  }
  g_warmupSteps[motor] = (uint8_t)steps;
  g_warmed[motor] = false;
  Serial.println(F("OK"));
}

static void handleWarmupCycles(const String &arg) {
  int motor = 0;
  long cycles = DEFAULT_WARMUP_CYCLES;
  if (!parseMotorValue(arg, motor, cycles, true, false, DEFAULT_WARMUP_CYCLES)) {
    Serial.println(F("ERR WARMUP_CYCLES format"));
    return;
  }
  if (!validateMotor(motor)) {
    return;
  }

  if (cycles < 0) {
    cycles = 0;
  }
  if (cycles > MAX_WARMUP_CYCLES) {
    cycles = MAX_WARMUP_CYCLES;
  }
  g_warmupCycles[motor] = (uint8_t)cycles;
  g_warmed[motor] = false;
  Serial.println(F("OK"));
}

static void handleHold(const String &arg) {
  int motor = 0;
  long enabled = 1;
  if (!parseMotorValue(arg, motor, enabled, true, true, 1)) {
    Serial.println(F("ERR HOLD format"));
    return;
  }
  if (!validateMotor(motor)) {
    return;
  }

  g_holdEnabled[motor] = (enabled != 0);
  if (!g_holdEnabled[motor]) {
    releaseMotor((uint8_t)motor);
  } else {
    applyPhase((uint8_t)motor, (uint8_t)g_phaseIdx[motor]);
  }
  Serial.println(F("OK"));
}

static void handleCali(const String &arg) {
  int motor = 0;
  long steps = 80;
  if (!parseMotorValue(arg, motor, steps, true, true, 80)) {
    Serial.println(F("ERR CALI format"));
    return;
  }
  if (!validateMotor(motor)) {
    return;
  }
  if (anyMotorActive()) {
    Serial.println(F("ERR BUSY"));
    return;
  }

  if (steps <= 0) {
    steps = 80;
  }
  if (steps > 20000) {
    steps = 20000;
  }

  uint8_t previousDelay = g_stepDelayMs[motor];
  if (g_stepDelayMs[motor] < 12) {
    g_stepDelayMs[motor] = 12;
  }

  Serial.print(F("CALI "));
  Serial.print(MOTOR_NAME[motor]);
  Serial.print(F(" "));
  Serial.println(steps);

  moveRaw((uint8_t)motor, steps);
  moveRaw((uint8_t)motor, -steps);
  if (!g_holdEnabled[motor]) {
    releaseMotor((uint8_t)motor);
  }
  g_stepDelayMs[motor] = previousDelay;
  g_warmed[motor] = true;
  Serial.println(F("OK"));
}

static void pauseOneMotor(uint8_t motorIdx) {
  if (g_moveActive[motorIdx]) {
    g_movePaused[motorIdx] = true;
  }
}

static void resumeOneMotor(uint8_t motorIdx) {
  if (g_moveActive[motorIdx] && g_movePaused[motorIdx]) {
    g_movePaused[motorIdx] = false;
    g_nextStepAtMs[motorIdx] = millis();
  }
}

static void handlePause(const String &arg) {
  int motor = 0;
  bool hasMotor = false;
  if (!parseOptionalMotor(arg, motor, hasMotor)) {
    Serial.println(F("ERR PAUSE format"));
    return;
  }

  if (hasMotor) {
    pauseOneMotor((uint8_t)motor);
  } else {
    for (uint8_t motorIdx = 0; motorIdx < MOTOR_COUNT; motorIdx++) {
      pauseOneMotor(motorIdx);
    }
  }
  Serial.println(F("OK PAUSED"));
}

static void handleResume(const String &arg) {
  int motor = 0;
  bool hasMotor = false;
  if (!parseOptionalMotor(arg, motor, hasMotor)) {
    Serial.println(F("ERR RESUME format"));
    return;
  }

  if (hasMotor) {
    resumeOneMotor((uint8_t)motor);
  } else {
    for (uint8_t motorIdx = 0; motorIdx < MOTOR_COUNT; motorIdx++) {
      resumeOneMotor(motorIdx);
    }
  }
  Serial.println(F("OK RUNNING"));
}

static void handleStatus(const String &arg) {
  int motor = 0;
  bool hasMotor = false;
  if (!parseOptionalMotor(arg, motor, hasMotor)) {
    Serial.println(F("ERR STATUS format"));
    return;
  }
  if (!validateMotor(motor)) {
    return;
  }

  Serial.print(F("STATUS "));
  if (!g_moveActive[motor]) {
    Serial.print(F("IDLE "));
  } else if (g_movePaused[motor]) {
    Serial.print(F("PAUSED "));
  } else {
    Serial.print(F("RUNNING "));
  }
  Serial.print(g_moveRequestedSteps[motor]);
  Serial.print(F(" "));
  Serial.print(g_moveExecutedSteps[motor]);
  Serial.print(F(" "));
  Serial.println(g_moveRemainingSteps[motor]);
}

static void stopOneMotor(uint8_t motorIdx) {
  g_moveActive[motorIdx] = false;
  g_movePaused[motorIdx] = false;
  g_moveRemainingSteps[motorIdx] = 0;
  g_warmed[motorIdx] = false;
  releaseMotor(motorIdx);
}

static void handleStop(const String &arg) {
  int motor = 0;
  bool hasMotor = false;
  if (!parseOptionalMotor(arg, motor, hasMotor)) {
    Serial.println(F("ERR STOP format"));
    return;
  }

  if (hasMotor) {
    stopOneMotor((uint8_t)motor);
  } else {
    for (uint8_t motorIdx = 0; motorIdx < MOTOR_COUNT; motorIdx++) {
      stopOneMotor(motorIdx);
    }
  }
  Serial.println(F("OK STOPPED"));
}

static void handleCommand(const String &line) {
  String cmd = line;
  cmd.trim();
  if (cmd.length() == 0) {
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
      handleHold("");
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

  if (cmd.startsWith(F("PAUSE"))) {
    int sp = cmd.indexOf(' ');
    if (sp < 0) {
      handlePause("");
      return;
    }
    handlePause(cmd.substring(sp + 1));
    return;
  }

  if (cmd.startsWith(F("RESUME"))) {
    int sp = cmd.indexOf(' ');
    if (sp < 0) {
      handleResume("");
      return;
    }
    handleResume(cmd.substring(sp + 1));
    return;
  }

  if (cmd.startsWith(F("STATUS"))) {
    int sp = cmd.indexOf(' ');
    if (sp < 0) {
      handleStatus("");
      return;
    }
    handleStatus(cmd.substring(sp + 1));
    return;
  }

  if (cmd.startsWith(F("STOP"))) {
    int sp = cmd.indexOf(' ');
    if (sp < 0) {
      handleStop("");
      return;
    }
    handleStop(cmd.substring(sp + 1));
    return;
  }

  Serial.println(F("ERR unknown"));
}

void setup() {
  for (uint8_t motorIdx = 0; motorIdx < MOTOR_COUNT; motorIdx++) {
    for (uint8_t pinIdx = 0; pinIdx < MOTOR_PIN_COUNT; pinIdx++) {
      pinMode(MOTOR_PIN[motorIdx][pinIdx], OUTPUT);
    }

    releaseMotor(motorIdx);
    g_phaseIdx[motorIdx] = 0;
    g_stepDelayMs[motorIdx] = DEFAULT_STEP_DELAY_MS;
    g_warmupSteps[motorIdx] = DEFAULT_WARMUP_STEPS;
    g_warmupCycles[motorIdx] = DEFAULT_WARMUP_CYCLES;
    g_dirSign[motorIdx] = 1;
    g_holdEnabled[motorIdx] = true;
    g_autoWarmupEnabled[motorIdx] = true;
    g_warmed[motorIdx] = false;
  }

  Serial.begin(115200);
  delay(300);
  Serial.println(F("READY XY"));
}

void loop() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n') {
      handleCommand(g_line);
      g_line = "";
    } else if (c != '\r') {
      g_line += c;
      if (g_line.length() > 128) {
        g_line = "";
      }
    }
  }

  serviceAllMotors();
}
