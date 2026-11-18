// 28BYJ-48 + ULN2003 XY 精簡版控制器
// motor 0 = X 軸，motor 1 = Y 軸
//
// 接線：
//   X 軸：IN1=D4, IN2=D5, IN3=D6, IN4=D7
//   Y 軸：IN1=D8, IN2=D9, IN3=D10, IN4=D11
//
// 常用指令，Serial baud rate = 115200：
//   PING                         -> PONG
//   MOVE <steps>                 -> 舊格式，控制 X 軸
//   MOVE <motor> <steps>         -> motor 0=X, 1=Y
//   SPEED_MS <ms>                -> 舊格式，設定 X 軸速度
//   SPEED_MS <motor> <ms>        -> 設定指定軸速度
//   DIR <sign>                   -> 舊格式，設定 X 軸方向，1 或 -1
//   DIR <motor> <sign>           -> 設定指定軸方向
//   HOLD <0|1>                   -> 舊格式，設定 X 軸是否保持通電
//   HOLD <motor> <0|1>           -> 設定指定軸是否保持通電
//   STATUS [motor]               -> 回報 IDLE 狀態
//   STOP [motor]                 -> 釋放指定軸；不帶 motor 時釋放兩軸

#include <Arduino.h>

const uint8_t MOTOR_COUNT = 2;
const uint8_t PIN_COUNT = 4;

// motor 0 = X，motor 1 = Y。
const uint8_t MOTOR_PINS[MOTOR_COUNT][PIN_COUNT] = {
  {4, 5, 6, 7},
  {8, 9, 10, 11},
};

// 28BYJ-48 半步進序列，適合顯微鏡載台微小移動。
const uint8_t HALF_STEP[8][PIN_COUNT] = {
  {1, 0, 0, 0},
  {1, 1, 0, 0},
  {0, 1, 0, 0},
  {0, 1, 1, 0},
  {0, 0, 1, 0},
  {0, 0, 1, 1},
  {0, 0, 0, 1},
  {1, 0, 0, 1},
};

int8_t phaseIndex[MOTOR_COUNT] = {0, 0};       // 目前半步進相位。
int8_t directionSign[MOTOR_COUNT] = {1, 1};    // 方向反轉設定。
uint8_t stepDelayMs[MOTOR_COUNT] = {5, 5};     // 每一步延遲時間。
bool holdEnabled[MOTOR_COUNT] = {true, true};  // 移動後是否保持通電。

String serialLine;
bool stopRequested = false;

int parseMotor(String text) {
  text.trim();
  if (text == "0") return 0;
  if (text == "1") return 1;
  return -1;
}

// 支援「<value>」與「<motor> <value>」兩種格式。
bool parseMotorValue(String text, int &motor, long &value) {
  text.trim();
  int splitAt = text.indexOf(' ');

  if (splitAt < 0) {
    motor = 0;
    value = text.toInt();
    return text.length() > 0;
  }

  motor = parseMotor(text.substring(0, splitAt));
  value = text.substring(splitAt + 1).toInt();
  return motor >= 0;
}

bool parseOptionalMotor(String text, int &motor, bool &hasMotor) {
  text.trim();
  hasMotor = text.length() > 0;
  if (!hasMotor) {
    motor = 0;
    return true;
  }
  motor = parseMotor(text);
  return motor >= 0;
}

void writePhase(int motor, int phase) {
  phase &= 7;
  for (uint8_t pin = 0; pin < PIN_COUNT; pin++) {
    digitalWrite(MOTOR_PINS[motor][pin], HALF_STEP[phase][pin] ? HIGH : LOW);
  }
}

void releaseMotor(int motor) {
  for (uint8_t pin = 0; pin < PIN_COUNT; pin++) {
    digitalWrite(MOTOR_PINS[motor][pin], LOW);
  }
}

void releaseAllMotors() {
  releaseMotor(0);
  releaseMotor(1);
}

void stepOnce(int motor, int dir) {
  phaseIndex[motor] += dir;
  if (phaseIndex[motor] < 0) phaseIndex[motor] = 7;
  if (phaseIndex[motor] > 7) phaseIndex[motor] = 0;
  writePhase(motor, phaseIndex[motor]);
  delay(stepDelayMs[motor]);
}

void pollStop() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n') {
      serialLine.trim();
      if (serialLine.startsWith("STOP")) {
        stopRequested = true;
        Serial.println(F("OK STOPPING"));
      }
      serialLine = "";
    } else if (c != '\r') {
      serialLine += c;
      if (serialLine.length() > 96) serialLine = "";
    }
  }
}

void moveMotor(int motor, long steps) {
  if (motor < 0 || motor >= MOTOR_COUNT) {
    Serial.println(F("ERR invalid motor"));
    return;
  }
  if (steps == 0) {
    Serial.println(F("DONE 0"));
    return;
  }

  long count = abs(steps);
  int dir = (steps > 0 ? 1 : -1) * directionSign[motor];
  stopRequested = false;

  for (long i = 0; i < count; i++) {
    pollStop();
    if (stopRequested) break;
    stepOnce(motor, dir);
  }

  if (!holdEnabled[motor]) releaseMotor(motor);
  Serial.print(F("DONE "));
  Serial.println(stopRequested ? 0 : steps);
}

void handleMove(String args) {
  int motor = 0;
  long steps = 0;
  if (!parseMotorValue(args, motor, steps)) {
    Serial.println(F("ERR MOVE format"));
    return;
  }
  moveMotor(motor, steps);
}

void handleSpeed(String args) {
  int motor = 0;
  long ms = 5;
  if (!parseMotorValue(args, motor, ms)) {
    Serial.println(F("ERR SPEED_MS format"));
    return;
  }
  if (motor < 0 || motor >= MOTOR_COUNT) {
    Serial.println(F("ERR invalid motor"));
    return;
  }
  stepDelayMs[motor] = constrain(ms, 1, 250);
  Serial.println(F("OK"));
}

void handleDirection(String args) {
  int motor = 0;
  long sign = 1;
  if (!parseMotorValue(args, motor, sign)) {
    Serial.println(F("ERR DIR format"));
    return;
  }
  if (motor < 0 || motor >= MOTOR_COUNT) {
    Serial.println(F("ERR invalid motor"));
    return;
  }
  directionSign[motor] = (sign >= 0) ? 1 : -1;
  Serial.println(F("OK"));
}

void handleHold(String args) {
  int motor = 0;
  long enabled = 1;
  if (!parseMotorValue(args, motor, enabled)) {
    Serial.println(F("ERR HOLD format"));
    return;
  }
  if (motor < 0 || motor >= MOTOR_COUNT) {
    Serial.println(F("ERR invalid motor"));
    return;
  }
  holdEnabled[motor] = enabled != 0;
  if (!holdEnabled[motor]) releaseMotor(motor);
  Serial.println(F("OK"));
}

void handleStatus(String args) {
  int motor = 0;
  bool hasMotor = false;
  if (!parseOptionalMotor(args, motor, hasMotor)) {
    Serial.println(F("ERR STATUS format"));
    return;
  }
  if (hasMotor && (motor < 0 || motor >= MOTOR_COUNT)) {
    Serial.println(F("ERR invalid motor"));
    return;
  }
  Serial.println(F("STATUS IDLE 0 0 0"));
}

void handleStop(String args) {
  int motor = 0;
  bool hasMotor = false;
  if (!parseOptionalMotor(args, motor, hasMotor)) {
    Serial.println(F("ERR STOP format"));
    return;
  }

  stopRequested = true;
  if (hasMotor) releaseMotor(motor);
  else releaseAllMotors();
  Serial.println(F("OK STOPPED"));
}

void handleCommand(String line) {
  line.trim();
  if (line.length() == 0) return;

  if (line.equalsIgnoreCase("PING")) {
    Serial.println(F("PONG"));
    return;
  }

  int splitAt = line.indexOf(' ');
  String command = splitAt < 0 ? line : line.substring(0, splitAt);
  String args = splitAt < 0 ? "" : line.substring(splitAt + 1);

  if (command == "MOVE") handleMove(args);
  else if (command == "SPEED_MS") handleSpeed(args);
  else if (command == "DIR") handleDirection(args);
  else if (command == "HOLD") handleHold(args);
  else if (command == "STATUS") handleStatus(args);
  else if (command == "STOP") handleStop(args);
  else Serial.println(F("ERR unknown"));
}

void setup() {
  for (uint8_t motor = 0; motor < MOTOR_COUNT; motor++) {
    for (uint8_t pin = 0; pin < PIN_COUNT; pin++) {
      pinMode(MOTOR_PINS[motor][pin], OUTPUT);
    }
    releaseMotor(motor);
  }

  Serial.begin(115200);
  delay(300);
  Serial.println(F("READY XY SIMPLE"));
}

void loop() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n') {
      handleCommand(serialLine);
      serialLine = "";
    } else if (c != '\r') {
      serialLine += c;
      if (serialLine.length() > 96) serialLine = "";
    }
  }
}
