// 28BYJ-48 + ULN2003 Serial Controller (2 motors)
// - motor 0: D10 D11 D12 D13
// - motor 1: D4 D5 D6 D7
//
// Protocol (newline terminated):
// PING
// MOVE [motor] <steps>      ; motor optional, default 0
// SPEED_MS [motor] <ms>     ; 1..250 (ms per half-step), motor optional default 0
// DIR [motor] <1|-1>       ; set direction sign for one motor
// CALI [motor] <steps>     ; run forward then backward, steps optional default 80
// HOLD [motor] <0|1>       ; keep coils energized after MOVE, motor optional default 0
// STOP [motor]             ; release one motor, no arg => release both
//
// Replies:
// READY
// PONG
// OK
// DONE <signed_steps>
// ERR ...

#include <Arduino.h>

const uint8_t MOTOR_COUNT = 2;
const uint8_t MOTOR_PIN_COUNT = 4;

const uint8_t MOTOR_PIN[MOTOR_COUNT][MOTOR_PIN_COUNT] = {
  {10, 11, 12, 13},  // motor 0
  {4, 5, 6, 7},      // motor 1
};

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

const uint8_t DEFAULT_STEP_DELAY_MS = 5;
const uint8_t MAX_STEP_DELAY_MS = 250;
const uint8_t MIN_STEP_DELAY_MS = 1;

int8_t g_phaseIdx[MOTOR_COUNT] = {0, 0};
uint8_t g_stepDelayMs[MOTOR_COUNT] = {DEFAULT_STEP_DELAY_MS, DEFAULT_STEP_DELAY_MS};
int8_t g_dirSign[MOTOR_COUNT] = {1, 1};
bool g_holdEnabled[MOTOR_COUNT] = {true, true};
String g_line;

static int parseMotorIndex(String t) {
  t.trim();
  if (t.length() == 0) {
    return -1;
  }
  if (t.length() != 1) {
    return -1;
  }
  if (t.charAt(0) != '0' && t.charAt(0) != '1') {
    return -1;
  }
  return t.charAt(0) - '0';
}

static bool parseMotorAndValue(const String &arg, int &motorIdx, long &value, bool valueOptional, long defaultValue) {
  String t = arg;
  t.trim();

  int sp = t.indexOf(' ');
  if (sp < 0) {
    // no motor separator, treat as only value when allowed
    if (valueOptional) {
      motorIdx = 0;
      value = t.toInt();
      return true;
    }
    return false;
  }

  String first = t.substring(0, sp);
  String second = t.substring(sp + 1);
  first.trim();
  second.trim();

  int mi = parseMotorIndex(first);
  if (mi < 0) {
    return false;
  }
  if (second.length() == 0) {
    if (valueOptional) {
      motorIdx = mi;
      value = defaultValue;
      return true;
    }
    return false;
  }

  motorIdx = mi;
  value = second.toInt();
  return true;
}

static void applyPhase(uint8_t motorIdx, uint8_t phase) {
  const uint8_t *p = MOTOR_PIN[motorIdx];
  phase &= 7;
  digitalWrite(p[0], SEQ[phase][0] ? HIGH : LOW);
  digitalWrite(p[1], SEQ[phase][1] ? HIGH : LOW);
  digitalWrite(p[2], SEQ[phase][2] ? HIGH : LOW);
  digitalWrite(p[3], SEQ[phase][3] ? HIGH : LOW);
}

static void releaseMotor(uint8_t motorIdx) {
  const uint8_t *p = MOTOR_PIN[motorIdx];
  digitalWrite(p[0], LOW);
  digitalWrite(p[1], LOW);
  digitalWrite(p[2], LOW);
  digitalWrite(p[3], LOW);
}

static void releaseAllMotors() {
  for (uint8_t m = 0; m < MOTOR_COUNT; m++) {
    releaseMotor(m);
  }
}

static void moveSteps(int motorIdx, long steps) {
  if (motorIdx < 0 || motorIdx >= MOTOR_COUNT) {
    Serial.println(F("ERR invalid motor"));
    return;
  }

  if (steps == 0) {
    Serial.println(F("DONE 0"));
    return;
  }

  long n = steps;
  if (n < 0) {
    n = -n;
  }
  int8_t dir = (steps > 0) ? 1 : -1;
  dir *= g_dirSign[motorIdx];

  for (long i = 0; i < n; i++) {
    g_phaseIdx[motorIdx] += dir;
    if (g_phaseIdx[motorIdx] < 0) {
      g_phaseIdx[motorIdx] = 7;
    } else if (g_phaseIdx[motorIdx] > 7) {
      g_phaseIdx[motorIdx] = 0;
    }
    applyPhase((uint8_t)motorIdx, (uint8_t)g_phaseIdx[motorIdx]);
    delay(g_stepDelayMs[motorIdx]);
  }

  if (!g_holdEnabled[motorIdx]) {
    releaseMotor((uint8_t)motorIdx);
  }
  Serial.print(F("DONE "));
  Serial.println(steps);
}

static void handleMove(const String &arg) {
  int motor = 0;
  long steps = 0;
  if (!parseMotorAndValue(arg, motor, steps, true, 0)) {
    Serial.println(F("ERR MOVE format"));
    return;
  }
  if (motor < 0 || motor >= MOTOR_COUNT) {
    Serial.println(F("ERR invalid motor"));
    return;
  }
  moveSteps(motor, steps);
}

static void handleSpeed(const String &arg) {
  int motor = 0;
  long ms = DEFAULT_STEP_DELAY_MS;
  if (!parseMotorAndValue(arg, motor, ms, true, DEFAULT_STEP_DELAY_MS)) {
    Serial.println(F("ERR SPEED_MS format"));
    return;
  }
  if (motor < 0 || motor >= MOTOR_COUNT) {
    Serial.println(F("ERR invalid motor"));
    return;
  }
  if (ms < MIN_STEP_DELAY_MS) ms = MIN_STEP_DELAY_MS;
  if (ms > MAX_STEP_DELAY_MS) ms = MAX_STEP_DELAY_MS;
  g_stepDelayMs[motor] = (uint8_t)ms;
  Serial.println(F("OK"));
}

static void handleDir(const String &arg) {
  String t = arg;
  t.trim();

  int sp = t.indexOf(' ');
  if (sp < 0) {
    Serial.println(F("ERR DIR format"));
    return;
  }
  int motor = parseMotorIndex(t.substring(0, sp));
  String signText = t.substring(sp + 1);
  signText.trim();
  if (motor < 0 || signText.length() == 0) {
    Serial.println(F("ERR DIR format"));
    return;
  }
  int sign = signText.toInt();
  g_dirSign[motor] = (sign >= 0) ? 1 : -1;
  Serial.println(F("OK"));
}

static void handleCali(const String &arg) {
  int motor = 0;
  long steps = 80;
  if (!parseMotorAndValue(arg, motor, steps, true, 80)) {
    Serial.println(F("ERR CALI format"));
    return;
  }
  if (motor < 0 || motor >= MOTOR_COUNT) {
    Serial.println(F("ERR invalid motor"));
    return;
  }
  if (steps <= 0) steps = 80;
  if (steps > 20000) steps = 20000;

  uint8_t prevDelay = g_stepDelayMs[motor];
  if (g_stepDelayMs[motor] < 12) {
    g_stepDelayMs[motor] = 12;  // slower and smoother for test
  }

  Serial.print(F("CALI "));
  Serial.print(motor);
  Serial.print(F(" "));
  Serial.println(steps);

  moveSteps(motor, steps);
  delay(50);
  moveSteps(motor, -steps);

  g_stepDelayMs[motor] = prevDelay;
  Serial.println(F("OK"));
}

static void handleHold(const String &arg) {
  int motor = 0;
  long enabled = 1;
  if (!parseMotorAndValue(arg, motor, enabled, true, 1)) {
    Serial.println(F("ERR HOLD format"));
    return;
  }
  if (motor < 0 || motor >= MOTOR_COUNT) {
    Serial.println(F("ERR invalid motor"));
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

static void handleStop(const String &arg) {
  String t = arg;
  t.trim();
  if (t.length() == 0) {
    releaseAllMotors();
    Serial.println(F("OK"));
    return;
  }
  int motor = parseMotorIndex(t);
  if (motor < 0) {
    Serial.println(F("ERR STOP format"));
    return;
  }
  releaseMotor((uint8_t)motor);
  Serial.println(F("OK"));
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

  if (cmd.startsWith(F("CALI"))) {
    int sp = cmd.indexOf(' ');
    if (sp < 0) {
      handleCali("");
      return;
    }
    handleCali(cmd.substring(sp + 1));
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
  for (uint8_t m = 0; m < MOTOR_COUNT; m++) {
    for (uint8_t i = 0; i < MOTOR_PIN_COUNT; i++) {
      pinMode(MOTOR_PIN[m][i], OUTPUT);
    }
    releaseMotor((uint8_t)m);
    g_phaseIdx[m] = 0;
    g_stepDelayMs[m] = DEFAULT_STEP_DELAY_MS;
    g_dirSign[m] = 1;
    g_holdEnabled[m] = true;
  }

  Serial.begin(115200);
  delay(300);
  Serial.println(F("READY"));
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
}
