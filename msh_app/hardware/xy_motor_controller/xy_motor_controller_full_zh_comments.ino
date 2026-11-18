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

#include <Arduino.h>  // 載入 Arduino 核心函式庫。

const uint8_t MOTOR_COUNT = 2;  // 設定固定參數。
const uint8_t MOTOR_PIN_COUNT = 4;  // 設定固定參數。

const char *MOTOR_NAME[MOTOR_COUNT] = {"X", "Y"};  // 設定固定參數。

// motor 0 = X, motor 1 = Y
const uint8_t MOTOR_PIN[MOTOR_COUNT][MOTOR_PIN_COUNT] = {  // 設定固定參數。
  {4, 5, 6, 7},  // 設定馬達接腳群組。
  {8, 9, 10, 11},  // 設定馬達接腳群組。
};  // 程式區塊邊界。

// 28BYJ-48 half-step sequence. 8 相比 full-step 更適合顯微鏡載台微小移動。
const uint8_t HALF_STEP_SEQ[8][4] = {  // 設定 half-step 相位表。
  {1, 0, 0, 0},  // 設定此相位的四線圈輸出。
  {1, 1, 0, 0},  // 設定此相位的四線圈輸出。
  {0, 1, 0, 0},  // 設定此相位的四線圈輸出。
  {0, 1, 1, 0},  // 設定此相位的四線圈輸出。
  {0, 0, 1, 0},  // 設定此相位的四線圈輸出。
  {0, 0, 1, 1},  // 設定此相位的四線圈輸出。
  {0, 0, 0, 1},  // 設定此相位的四線圈輸出。
  {1, 0, 0, 1},  // 設定此相位的四線圈輸出。
};  // 程式區塊邊界。

const uint8_t DEFAULT_STEP_DELAY_MS = 5;  // 設定固定參數。
const uint8_t MIN_STEP_DELAY_MS = 1;  // 設定固定參數。
const uint8_t MAX_STEP_DELAY_MS = 250;  // 設定固定參數。
const uint8_t DEFAULT_WARMUP_STEPS = 80;  // 設定固定參數。
const uint8_t DEFAULT_WARMUP_CYCLES = 1;  // 設定固定參數。
const uint8_t MAX_WARMUP_STEPS = 80;  // 設定固定參數。
const uint8_t MAX_WARMUP_CYCLES = 10;  // 設定固定參數。
const uint8_t WARMUP_MIN_DELAY_MS = 8;  // 設定固定參數。

int8_t g_phaseIdx[MOTOR_COUNT] = {0, 0};  // 宣告全域狀態變數。
uint8_t g_stepDelayMs[MOTOR_COUNT] = {DEFAULT_STEP_DELAY_MS, DEFAULT_STEP_DELAY_MS};  // 宣告全域狀態變數。
uint8_t g_warmupSteps[MOTOR_COUNT] = {DEFAULT_WARMUP_STEPS, DEFAULT_WARMUP_STEPS};  // 宣告全域狀態變數。
uint8_t g_warmupCycles[MOTOR_COUNT] = {DEFAULT_WARMUP_CYCLES, DEFAULT_WARMUP_CYCLES};  // 宣告全域狀態變數。
int8_t g_dirSign[MOTOR_COUNT] = {1, 1};  // 宣告全域狀態變數。
bool g_holdEnabled[MOTOR_COUNT] = {true, true};  // 宣告全域狀態變數。
bool g_autoWarmupEnabled[MOTOR_COUNT] = {true, true};  // 宣告全域狀態變數。
bool g_warmed[MOTOR_COUNT] = {false, false};  // 宣告全域狀態變數。

bool g_moveActive[MOTOR_COUNT] = {false, false};  // 宣告全域狀態變數。
bool g_movePaused[MOTOR_COUNT] = {false, false};  // 宣告全域狀態變數。
long g_moveRequestedSteps[MOTOR_COUNT] = {0, 0};  // 宣告全域狀態變數。
long g_moveExecutedSteps[MOTOR_COUNT] = {0, 0};  // 宣告全域狀態變數。
long g_moveRemainingSteps[MOTOR_COUNT] = {0, 0};  // 宣告全域狀態變數。
int8_t g_moveDirection[MOTOR_COUNT] = {1, 1};  // 宣告全域狀態變數。
unsigned long g_nextStepAtMs[MOTOR_COUNT] = {0, 0};  // 宣告全域狀態變數。

String g_line;  // 宣告全域狀態變數。

static int parseMotorIndex(String text) {  // 定義函式。
  text.trim();  // 移除字串前後空白。
  if (text.length() != 1) {  // 判斷條件是否成立。
    return -1;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。
  char c = text.charAt(0);  // 設定變數值。
  if (c != '0' && c != '1') {  // 判斷條件是否成立。
    return -1;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。
  return c - '0';  // 回傳結果或離開函式。
}  // 程式區塊邊界。

// 解析「<value>」或「<motor> <value>」格式。
// allowBareValue=true 時，單一數字會被視為 motor 0 的 value，以保留舊版單軸指令相容性。
static bool parseMotorValue(  // 定義函式。
  const String &arg,  // 設定固定參數。
  int &motorIdx,  // 執行此行控制邏輯。
  long &value,  // 執行此行控制邏輯。
  bool allowBareValue,  // 執行此行控制邏輯。
  bool allowMissingValue,  // 執行此行控制邏輯。
  long defaultValue  // 執行此行控制邏輯。
) {  // 執行此行控制邏輯。
  String text = arg;  // 設定變數值。
  text.trim();  // 移除字串前後空白。

  if (text.length() == 0) {  // 判斷條件是否成立。
    if (!allowMissingValue) {  // 判斷條件是否成立。
      return false;  // 回傳結果或離開函式。
    }  // 程式區塊邊界。
    motorIdx = 0;  // 設定變數值。
    value = defaultValue;  // 設定變數值。
    return true;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  int sp = text.indexOf(' ');  // 拆解或轉換指令參數。
  if (sp < 0) {  // 判斷條件是否成立。
    if (allowBareValue) {  // 判斷條件是否成立。
      motorIdx = 0;  // 設定變數值。
      value = text.toInt();  // 拆解或轉換指令參數。
      return true;  // 回傳結果或離開函式。
    }  // 程式區塊邊界。
    int maybeMotor = parseMotorIndex(text);  // 設定變數值。
    if (allowMissingValue && maybeMotor >= 0) {  // 判斷條件是否成立。
      motorIdx = maybeMotor;  // 設定變數值。
      value = defaultValue;  // 設定變數值。
      return true;  // 回傳結果或離開函式。
    }  // 程式區塊邊界。
    return false;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  String first = text.substring(0, sp);  // 拆解或轉換指令參數。
  String rest = text.substring(sp + 1);  // 拆解或轉換指令參數。
  first.trim();  // 移除字串前後空白。
  rest.trim();  // 移除字串前後空白。

  int parsedMotor = parseMotorIndex(first);  // 設定變數值。
  if (parsedMotor < 0) {  // 判斷條件是否成立。
    return false;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  motorIdx = parsedMotor;  // 設定變數值。
  if (rest.length() == 0) {  // 判斷條件是否成立。
    if (!allowMissingValue) {  // 判斷條件是否成立。
      return false;  // 回傳結果或離開函式。
    }  // 程式區塊邊界。
    value = defaultValue;  // 設定變數值。
    return true;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  value = rest.toInt();  // 拆解或轉換指令參數。
  return true;  // 回傳結果或離開函式。
}  // 程式區塊邊界。

static bool parseOptionalMotor(const String &arg, int &motorIdx, bool &hasMotor) {  // 定義函式。
  String text = arg;  // 設定變數值。
  text.trim();  // 移除字串前後空白。
  if (text.length() == 0) {  // 判斷條件是否成立。
    motorIdx = 0;  // 設定變數值。
    hasMotor = false;  // 設定變數值。
    return true;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  int parsedMotor = parseMotorIndex(text);  // 設定變數值。
  if (parsedMotor < 0) {  // 判斷條件是否成立。
    return false;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  motorIdx = parsedMotor;  // 設定變數值。
  hasMotor = true;  // 設定變數值。
  return true;  // 回傳結果或離開函式。
}  // 程式區塊邊界。

static bool validateMotor(int motorIdx) {  // 定義函式。
  if (motorIdx < 0 || motorIdx >= MOTOR_COUNT) {  // 判斷條件是否成立。
    Serial.println(F("ERR invalid motor"));  // 透過 Serial 輸出回覆。
    return false;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。
  return true;  // 回傳結果或離開函式。
}  // 程式區塊邊界。

static void applyPhase(uint8_t motorIdx, uint8_t phase) {  // 定義函式。
  phase &= 7;  // 設定變數值。
  for (uint8_t pinIdx = 0; pinIdx < MOTOR_PIN_COUNT; pinIdx++) {  // 使用迴圈逐一處理。
    digitalWrite(  // 控制 Arduino 腳位高低電位。
      MOTOR_PIN[motorIdx][pinIdx],  // 執行此行控制邏輯。
      HALF_STEP_SEQ[phase][pinIdx] ? HIGH : LOW  // 執行此行控制邏輯。
    );  // 執行此行控制邏輯。
  }  // 程式區塊邊界。
}  // 程式區塊邊界。

static void releaseMotor(uint8_t motorIdx) {  // 定義函式。
  for (uint8_t pinIdx = 0; pinIdx < MOTOR_PIN_COUNT; pinIdx++) {  // 使用迴圈逐一處理。
    digitalWrite(MOTOR_PIN[motorIdx][pinIdx], LOW);  // 控制 Arduino 腳位高低電位。
  }  // 程式區塊邊界。
}  // 程式區塊邊界。

static void releaseAllMotors() {  // 定義函式。
  for (uint8_t motorIdx = 0; motorIdx < MOTOR_COUNT; motorIdx++) {  // 使用迴圈逐一處理。
    releaseMotor(motorIdx);  // 執行此行控制邏輯。
  }  // 程式區塊邊界。
}  // 程式區塊邊界。

static void applyStep(uint8_t motorIdx, int8_t dir) {  // 定義函式。
  int16_t nextPhase = (int16_t)g_phaseIdx[motorIdx] + dir;  // 更新全域狀態值。
  if (nextPhase < 0) {  // 判斷條件是否成立。
    nextPhase = 7;  // 設定變數值。
  } else if (nextPhase > 7) {  // 程式區塊邊界。
    nextPhase = 0;  // 設定變數值。
  }  // 程式區塊邊界。
  g_phaseIdx[motorIdx] = (int8_t)nextPhase;  // 更新全域狀態值。
  applyPhase(motorIdx, (uint8_t)g_phaseIdx[motorIdx]);  // 執行此行控制邏輯。
}  // 程式區塊邊界。

static void stepRaw(uint8_t motorIdx, int8_t dir) {  // 定義函式。
  applyStep(motorIdx, dir);  // 執行此行控制邏輯。
  delay(g_stepDelayMs[motorIdx]);  // 短暫等待讓動作穩定。
}  // 程式區塊邊界。

static void moveRaw(uint8_t motorIdx, long steps) {  // 定義函式。
  if (steps == 0) {  // 判斷條件是否成立。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  long count = steps;  // 設定變數值。
  if (count < 0) {  // 判斷條件是否成立。
    count = -count;  // 設定變數值。
  }  // 程式區塊邊界。

  int8_t dir = (steps > 0) ? 1 : -1;  // 設定變數值。
  dir *= g_dirSign[motorIdx];  // 更新全域狀態值。

  for (long i = 0; i < count; i++) {  // 使用迴圈逐一處理。
    stepRaw(motorIdx, dir);  // 執行此行控制邏輯。
  }  // 程式區塊邊界。
}  // 程式區塊邊界。

static bool anyMotorActive() {  // 定義函式。
  for (uint8_t motorIdx = 0; motorIdx < MOTOR_COUNT; motorIdx++) {  // 使用迴圈逐一處理。
    if (g_moveActive[motorIdx]) {  // 判斷條件是否成立。
      return true;  // 回傳結果或離開函式。
    }  // 程式區塊邊界。
  }  // 程式區塊邊界。
  return false;  // 回傳結果或離開函式。
}  // 程式區塊邊界。

static void runWarmup(uint8_t motorIdx, uint8_t steps, uint8_t cycles) {  // 定義函式。
  if (steps < 1) {  // 判斷條件是否成立。
    steps = 1;  // 設定變數值。
  }  // 程式區塊邊界。
  if (steps > MAX_WARMUP_STEPS) {  // 判斷條件是否成立。
    steps = MAX_WARMUP_STEPS;  // 設定變數值。
  }  // 程式區塊邊界。
  if (cycles > MAX_WARMUP_CYCLES) {  // 判斷條件是否成立。
    cycles = MAX_WARMUP_CYCLES;  // 設定變數值。
  }  // 程式區塊邊界。
  if (cycles == 0) {  // 判斷條件是否成立。
    g_warmed[motorIdx] = true;  // 更新全域狀態值。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  uint8_t previousDelay = g_stepDelayMs[motorIdx];  // 更新全域狀態值。
  if (g_stepDelayMs[motorIdx] < WARMUP_MIN_DELAY_MS) {  // 判斷條件是否成立。
    g_stepDelayMs[motorIdx] = WARMUP_MIN_DELAY_MS;  // 更新全域狀態值。
  }  // 程式區塊邊界。

  for (uint8_t cycle = 0; cycle < cycles; cycle++) {  // 使用迴圈逐一處理。
    moveRaw(motorIdx, steps);  // 執行此行控制邏輯。
    delay(20);  // 短暫等待讓動作穩定。
    moveRaw(motorIdx, -steps);  // 執行此行控制邏輯。
    delay(20);  // 短暫等待讓動作穩定。
  }  // 程式區塊邊界。

  g_stepDelayMs[motorIdx] = previousDelay;  // 更新全域狀態值。
  if (!g_holdEnabled[motorIdx]) {  // 判斷條件是否成立。
    releaseMotor(motorIdx);  // 執行此行控制邏輯。
  }  // 程式區塊邊界。
  g_warmed[motorIdx] = true;  // 更新全域狀態值。
}  // 程式區塊邊界。

static void finishActiveMove(uint8_t motorIdx) {  // 定義函式。
  long completed = g_moveRequestedSteps[motorIdx];  // 更新全域狀態值。
  g_moveActive[motorIdx] = false;  // 更新全域狀態值。
  g_movePaused[motorIdx] = false;  // 更新全域狀態值。
  g_moveRemainingSteps[motorIdx] = 0;  // 更新全域狀態值。
  if (!g_holdEnabled[motorIdx]) {  // 判斷條件是否成立。
    releaseMotor(motorIdx);  // 執行此行控制邏輯。
  }  // 程式區塊邊界。

  Serial.print(F("DONE "));  // 透過 Serial 輸出回覆。
  Serial.println(completed);  // 透過 Serial 輸出回覆。
}  // 程式區塊邊界。

static void serviceMotor(uint8_t motorIdx) {  // 定義函式。
  if (!g_moveActive[motorIdx] || g_movePaused[motorIdx]) {  // 判斷條件是否成立。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  unsigned long now = millis();  // 讀取 Arduino 累計毫秒時間。
  if ((long)(now - g_nextStepAtMs[motorIdx]) < 0) {  // 判斷條件是否成立。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  applyStep(motorIdx, g_moveDirection[motorIdx]);  // 執行此行控制邏輯。
  g_moveExecutedSteps[motorIdx]++;  // 執行此行控制邏輯。
  g_moveRemainingSteps[motorIdx]--;  // 執行此行控制邏輯。

  if (g_moveRemainingSteps[motorIdx] <= 0) {  // 判斷條件是否成立。
    finishActiveMove(motorIdx);  // 執行此行控制邏輯。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  g_nextStepAtMs[motorIdx] = now + g_stepDelayMs[motorIdx];  // 更新全域狀態值。
}  // 程式區塊邊界。

static void serviceAllMotors() {  // 定義函式。
  for (uint8_t motorIdx = 0; motorIdx < MOTOR_COUNT; motorIdx++) {  // 使用迴圈逐一處理。
    serviceMotor(motorIdx);  // 執行此行控制邏輯。
  }  // 程式區塊邊界。
}  // 程式區塊邊界。

static void startMove(uint8_t motorIdx, long steps) {  // 定義函式。
  if (steps == 0) {  // 判斷條件是否成立。
    Serial.println(F("DONE 0"));  // 透過 Serial 輸出回覆。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。
  if (g_moveActive[motorIdx]) {  // 判斷條件是否成立。
    Serial.println(F("ERR BUSY"));  // 透過 Serial 輸出回覆。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  if (g_autoWarmupEnabled[motorIdx] && !g_warmed[motorIdx]) {  // 判斷條件是否成立。
    runWarmup(motorIdx, g_warmupSteps[motorIdx], g_warmupCycles[motorIdx]);  // 執行此行控制邏輯。
  }  // 程式區塊邊界。

  g_moveRequestedSteps[motorIdx] = steps;  // 更新全域狀態值。
  g_moveExecutedSteps[motorIdx] = 0;  // 更新全域狀態值。
  g_moveRemainingSteps[motorIdx] = (steps < 0) ? -steps : steps;  // 更新全域狀態值。
  g_moveDirection[motorIdx] = (steps > 0) ? 1 : -1;  // 更新全域狀態值。
  g_moveDirection[motorIdx] *= g_dirSign[motorIdx];  // 更新全域狀態值。
  g_movePaused[motorIdx] = false;  // 更新全域狀態值。
  g_moveActive[motorIdx] = true;  // 更新全域狀態值。
  g_nextStepAtMs[motorIdx] = millis();  // 讀取 Arduino 累計毫秒時間。
}  // 程式區塊邊界。

static void handleMove(const String &arg) {  // 定義指令處理函式。
  int motor = 0;  // 設定變數值。
  long steps = 0;  // 設定變數值。
  if (!parseMotorValue(arg, motor, steps, true, false, 0)) {  // 判斷條件是否成立。
    Serial.println(F("ERR MOVE format"));  // 透過 Serial 輸出回覆。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。
  if (!validateMotor(motor)) {  // 判斷條件是否成立。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。
  startMove((uint8_t)motor, steps);  // 執行此行控制邏輯。
}  // 程式區塊邊界。

static void handleSpeed(const String &arg) {  // 定義指令處理函式。
  int motor = 0;  // 設定變數值。
  long ms = DEFAULT_STEP_DELAY_MS;  // 設定變數值。
  if (!parseMotorValue(arg, motor, ms, true, false, DEFAULT_STEP_DELAY_MS)) {  // 判斷條件是否成立。
    Serial.println(F("ERR SPEED_MS format"));  // 透過 Serial 輸出回覆。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。
  if (!validateMotor(motor)) {  // 判斷條件是否成立。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  if (ms < MIN_STEP_DELAY_MS) {  // 判斷條件是否成立。
    ms = MIN_STEP_DELAY_MS;  // 設定變數值。
  }  // 程式區塊邊界。
  if (ms > MAX_STEP_DELAY_MS) {  // 判斷條件是否成立。
    ms = MAX_STEP_DELAY_MS;  // 設定變數值。
  }  // 程式區塊邊界。

  g_stepDelayMs[motor] = (uint8_t)ms;  // 更新全域狀態值。
  Serial.println(F("OK"));  // 透過 Serial 輸出回覆。
}  // 程式區塊邊界。

static void handleDir(const String &arg) {  // 定義指令處理函式。
  int motor = 0;  // 設定變數值。
  long sign = 1;  // 設定變數值。
  if (!parseMotorValue(arg, motor, sign, true, false, 1)) {  // 判斷條件是否成立。
    Serial.println(F("ERR DIR format"));  // 透過 Serial 輸出回覆。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。
  if (!validateMotor(motor)) {  // 判斷條件是否成立。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  g_dirSign[motor] = (sign >= 0) ? 1 : -1;  // 更新全域狀態值。
  g_warmed[motor] = false;  // 更新全域狀態值。
  Serial.println(F("OK"));  // 透過 Serial 輸出回覆。
}  // 程式區塊邊界。

static void handleWarmup(const String &arg) {  // 定義指令處理函式。
  int motor = 0;  // 設定變數值。
  long steps = DEFAULT_WARMUP_STEPS;  // 設定變數值。
  long cycles = DEFAULT_WARMUP_CYCLES;  // 設定變數值。
  String text = arg;  // 設定變數值。
  text.trim();  // 移除字串前後空白。

  if (anyMotorActive()) {  // 判斷條件是否成立。
    Serial.println(F("ERR BUSY"));  // 透過 Serial 輸出回覆。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  if (text.length() > 0) {  // 判斷條件是否成立。
    int firstSpace = text.indexOf(' ');  // 拆解或轉換指令參數。
    if (firstSpace < 0) {  // 判斷條件是否成立。
      // WARMUP 40：舊格式，X 軸暖機 40 steps。
      steps = text.toInt();  // 拆解或轉換指令參數。
    } else {  // 程式區塊邊界。
      String first = text.substring(0, firstSpace);  // 拆解或轉換指令參數。
      String rest = text.substring(firstSpace + 1);  // 拆解或轉換指令參數。
      first.trim();  // 移除字串前後空白。
      rest.trim();  // 移除字串前後空白。

      int parsedMotor = parseMotorIndex(first);  // 設定變數值。
      if (parsedMotor >= 0) {  // 判斷條件是否成立。
        motor = parsedMotor;  // 設定變數值。
        int secondSpace = rest.indexOf(' ');  // 拆解或轉換指令參數。
        if (secondSpace < 0) {  // 判斷條件是否成立。
          steps = rest.toInt();  // 拆解或轉換指令參數。
        } else {  // 程式區塊邊界。
          String stepText = rest.substring(0, secondSpace);  // 拆解或轉換指令參數。
          String cycleText = rest.substring(secondSpace + 1);  // 拆解或轉換指令參數。
          stepText.trim();  // 移除字串前後空白。
          cycleText.trim();  // 移除字串前後空白。
          steps = stepText.toInt();  // 拆解或轉換指令參數。
          if (cycleText.length() > 0) {  // 判斷條件是否成立。
            cycles = cycleText.toInt();  // 拆解或轉換指令參數。
          }  // 程式區塊邊界。
        }  // 程式區塊邊界。
      } else {  // 程式區塊邊界。
        // WARMUP 40 2：舊格式，X 軸 40 steps x 2 cycles。
        String stepText = first;  // 設定變數值。
        String cycleText = rest;  // 設定變數值。
        steps = stepText.toInt();  // 拆解或轉換指令參數。
        if (cycleText.length() > 0) {  // 判斷條件是否成立。
          cycles = cycleText.toInt();  // 拆解或轉換指令參數。
        }  // 程式區塊邊界。
      }  // 程式區塊邊界。
    }  // 程式區塊邊界。
  }  // 程式區塊邊界。

  if (!validateMotor(motor)) {  // 判斷條件是否成立。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。
  if (steps < 1) {  // 判斷條件是否成立。
    steps = 1;  // 設定變數值。
  }  // 程式區塊邊界。
  if (steps > MAX_WARMUP_STEPS) {  // 判斷條件是否成立。
    steps = MAX_WARMUP_STEPS;  // 設定變數值。
  }  // 程式區塊邊界。
  if (cycles < 0) {  // 判斷條件是否成立。
    cycles = 0;  // 設定變數值。
  }  // 程式區塊邊界。
  if (cycles > MAX_WARMUP_CYCLES) {  // 判斷條件是否成立。
    cycles = MAX_WARMUP_CYCLES;  // 設定變數值。
  }  // 程式區塊邊界。

  Serial.print(F("WARMUP "));  // 透過 Serial 輸出回覆。
  Serial.print(MOTOR_NAME[motor]);  // 透過 Serial 輸出回覆。
  Serial.print(F(" steps="));  // 透過 Serial 輸出回覆。
  Serial.print(steps);  // 透過 Serial 輸出回覆。
  Serial.print(F(" cycles="));  // 透過 Serial 輸出回覆。
  Serial.println(cycles);  // 透過 Serial 輸出回覆。

  runWarmup((uint8_t)motor, (uint8_t)steps, (uint8_t)cycles);  // 執行此行控制邏輯。
  Serial.println(F("OK"));  // 透過 Serial 輸出回覆。
}  // 程式區塊邊界。

static void handleAutoWarm(const String &arg) {  // 定義指令處理函式。
  int motor = 0;  // 設定變數值。
  long enabled = 1;  // 設定變數值。
  if (!parseMotorValue(arg, motor, enabled, true, false, 1)) {  // 判斷條件是否成立。
    Serial.println(F("ERR AUTOWARM format"));  // 透過 Serial 輸出回覆。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。
  if (!validateMotor(motor)) {  // 判斷條件是否成立。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  g_autoWarmupEnabled[motor] = (enabled != 0);  // 更新全域狀態值。
  if (!g_autoWarmupEnabled[motor]) {  // 判斷條件是否成立。
    g_warmed[motor] = true;  // 更新全域狀態值。
  }  // 程式區塊邊界。
  Serial.println(F("OK"));  // 透過 Serial 輸出回覆。
}  // 程式區塊邊界。

static void handleWarmupSteps(const String &arg) {  // 定義指令處理函式。
  int motor = 0;  // 設定變數值。
  long steps = DEFAULT_WARMUP_STEPS;  // 設定變數值。
  if (!parseMotorValue(arg, motor, steps, true, false, DEFAULT_WARMUP_STEPS)) {  // 判斷條件是否成立。
    Serial.println(F("ERR WARMUP_STEPS format"));  // 透過 Serial 輸出回覆。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。
  if (!validateMotor(motor)) {  // 判斷條件是否成立。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  if (steps < 1) {  // 判斷條件是否成立。
    steps = 1;  // 設定變數值。
  }  // 程式區塊邊界。
  if (steps > MAX_WARMUP_STEPS) {  // 判斷條件是否成立。
    steps = MAX_WARMUP_STEPS;  // 設定變數值。
  }  // 程式區塊邊界。
  g_warmupSteps[motor] = (uint8_t)steps;  // 更新全域狀態值。
  g_warmed[motor] = false;  // 更新全域狀態值。
  Serial.println(F("OK"));  // 透過 Serial 輸出回覆。
}  // 程式區塊邊界。

static void handleWarmupCycles(const String &arg) {  // 定義指令處理函式。
  int motor = 0;  // 設定變數值。
  long cycles = DEFAULT_WARMUP_CYCLES;  // 設定變數值。
  if (!parseMotorValue(arg, motor, cycles, true, false, DEFAULT_WARMUP_CYCLES)) {  // 判斷條件是否成立。
    Serial.println(F("ERR WARMUP_CYCLES format"));  // 透過 Serial 輸出回覆。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。
  if (!validateMotor(motor)) {  // 判斷條件是否成立。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  if (cycles < 0) {  // 判斷條件是否成立。
    cycles = 0;  // 設定變數值。
  }  // 程式區塊邊界。
  if (cycles > MAX_WARMUP_CYCLES) {  // 判斷條件是否成立。
    cycles = MAX_WARMUP_CYCLES;  // 設定變數值。
  }  // 程式區塊邊界。
  g_warmupCycles[motor] = (uint8_t)cycles;  // 更新全域狀態值。
  g_warmed[motor] = false;  // 更新全域狀態值。
  Serial.println(F("OK"));  // 透過 Serial 輸出回覆。
}  // 程式區塊邊界。

static void handleHold(const String &arg) {  // 定義指令處理函式。
  int motor = 0;  // 設定變數值。
  long enabled = 1;  // 設定變數值。
  if (!parseMotorValue(arg, motor, enabled, true, true, 1)) {  // 判斷條件是否成立。
    Serial.println(F("ERR HOLD format"));  // 透過 Serial 輸出回覆。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。
  if (!validateMotor(motor)) {  // 判斷條件是否成立。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  g_holdEnabled[motor] = (enabled != 0);  // 更新全域狀態值。
  if (!g_holdEnabled[motor]) {  // 判斷條件是否成立。
    releaseMotor((uint8_t)motor);  // 執行此行控制邏輯。
  } else {  // 程式區塊邊界。
    applyPhase((uint8_t)motor, (uint8_t)g_phaseIdx[motor]);  // 執行此行控制邏輯。
  }  // 程式區塊邊界。
  Serial.println(F("OK"));  // 透過 Serial 輸出回覆。
}  // 程式區塊邊界。

static void handleCali(const String &arg) {  // 定義指令處理函式。
  int motor = 0;  // 設定變數值。
  long steps = 80;  // 設定變數值。
  if (!parseMotorValue(arg, motor, steps, true, true, 80)) {  // 判斷條件是否成立。
    Serial.println(F("ERR CALI format"));  // 透過 Serial 輸出回覆。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。
  if (!validateMotor(motor)) {  // 判斷條件是否成立。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。
  if (anyMotorActive()) {  // 判斷條件是否成立。
    Serial.println(F("ERR BUSY"));  // 透過 Serial 輸出回覆。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  if (steps <= 0) {  // 判斷條件是否成立。
    steps = 80;  // 設定變數值。
  }  // 程式區塊邊界。
  if (steps > 20000) {  // 判斷條件是否成立。
    steps = 20000;  // 設定變數值。
  }  // 程式區塊邊界。

  uint8_t previousDelay = g_stepDelayMs[motor];  // 更新全域狀態值。
  if (g_stepDelayMs[motor] < 12) {  // 判斷條件是否成立。
    g_stepDelayMs[motor] = 12;  // 更新全域狀態值。
  }  // 程式區塊邊界。

  Serial.print(F("CALI "));  // 透過 Serial 輸出回覆。
  Serial.print(MOTOR_NAME[motor]);  // 透過 Serial 輸出回覆。
  Serial.print(F(" "));  // 透過 Serial 輸出回覆。
  Serial.println(steps);  // 透過 Serial 輸出回覆。

  moveRaw((uint8_t)motor, steps);  // 執行此行控制邏輯。
  moveRaw((uint8_t)motor, -steps);  // 執行此行控制邏輯。
  if (!g_holdEnabled[motor]) {  // 判斷條件是否成立。
    releaseMotor((uint8_t)motor);  // 執行此行控制邏輯。
  }  // 程式區塊邊界。
  g_stepDelayMs[motor] = previousDelay;  // 更新全域狀態值。
  g_warmed[motor] = true;  // 更新全域狀態值。
  Serial.println(F("OK"));  // 透過 Serial 輸出回覆。
}  // 程式區塊邊界。

static void pauseOneMotor(uint8_t motorIdx) {  // 定義函式。
  if (g_moveActive[motorIdx]) {  // 判斷條件是否成立。
    g_movePaused[motorIdx] = true;  // 更新全域狀態值。
  }  // 程式區塊邊界。
}  // 程式區塊邊界。

static void resumeOneMotor(uint8_t motorIdx) {  // 定義函式。
  if (g_moveActive[motorIdx] && g_movePaused[motorIdx]) {  // 判斷條件是否成立。
    g_movePaused[motorIdx] = false;  // 更新全域狀態值。
    g_nextStepAtMs[motorIdx] = millis();  // 讀取 Arduino 累計毫秒時間。
  }  // 程式區塊邊界。
}  // 程式區塊邊界。

static void handlePause(const String &arg) {  // 定義指令處理函式。
  int motor = 0;  // 設定變數值。
  bool hasMotor = false;  // 設定變數值。
  if (!parseOptionalMotor(arg, motor, hasMotor)) {  // 判斷條件是否成立。
    Serial.println(F("ERR PAUSE format"));  // 透過 Serial 輸出回覆。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  if (hasMotor) {  // 判斷條件是否成立。
    pauseOneMotor((uint8_t)motor);  // 執行此行控制邏輯。
  } else {  // 程式區塊邊界。
    for (uint8_t motorIdx = 0; motorIdx < MOTOR_COUNT; motorIdx++) {  // 使用迴圈逐一處理。
      pauseOneMotor(motorIdx);  // 執行此行控制邏輯。
    }  // 程式區塊邊界。
  }  // 程式區塊邊界。
  Serial.println(F("OK PAUSED"));  // 透過 Serial 輸出回覆。
}  // 程式區塊邊界。

static void handleResume(const String &arg) {  // 定義指令處理函式。
  int motor = 0;  // 設定變數值。
  bool hasMotor = false;  // 設定變數值。
  if (!parseOptionalMotor(arg, motor, hasMotor)) {  // 判斷條件是否成立。
    Serial.println(F("ERR RESUME format"));  // 透過 Serial 輸出回覆。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  if (hasMotor) {  // 判斷條件是否成立。
    resumeOneMotor((uint8_t)motor);  // 執行此行控制邏輯。
  } else {  // 程式區塊邊界。
    for (uint8_t motorIdx = 0; motorIdx < MOTOR_COUNT; motorIdx++) {  // 使用迴圈逐一處理。
      resumeOneMotor(motorIdx);  // 執行此行控制邏輯。
    }  // 程式區塊邊界。
  }  // 程式區塊邊界。
  Serial.println(F("OK RUNNING"));  // 透過 Serial 輸出回覆。
}  // 程式區塊邊界。

static void handleStatus(const String &arg) {  // 定義指令處理函式。
  int motor = 0;  // 設定變數值。
  bool hasMotor = false;  // 設定變數值。
  if (!parseOptionalMotor(arg, motor, hasMotor)) {  // 判斷條件是否成立。
    Serial.println(F("ERR STATUS format"));  // 透過 Serial 輸出回覆。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。
  if (!validateMotor(motor)) {  // 判斷條件是否成立。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  Serial.print(F("STATUS "));  // 透過 Serial 輸出回覆。
  if (!g_moveActive[motor]) {  // 判斷條件是否成立。
    Serial.print(F("IDLE "));  // 透過 Serial 輸出回覆。
  } else if (g_movePaused[motor]) {  // 程式區塊邊界。
    Serial.print(F("PAUSED "));  // 透過 Serial 輸出回覆。
  } else {  // 程式區塊邊界。
    Serial.print(F("RUNNING "));  // 透過 Serial 輸出回覆。
  }  // 程式區塊邊界。
  Serial.print(g_moveRequestedSteps[motor]);  // 透過 Serial 輸出回覆。
  Serial.print(F(" "));  // 透過 Serial 輸出回覆。
  Serial.print(g_moveExecutedSteps[motor]);  // 透過 Serial 輸出回覆。
  Serial.print(F(" "));  // 透過 Serial 輸出回覆。
  Serial.println(g_moveRemainingSteps[motor]);  // 透過 Serial 輸出回覆。
}  // 程式區塊邊界。

static void stopOneMotor(uint8_t motorIdx) {  // 定義函式。
  g_moveActive[motorIdx] = false;  // 更新全域狀態值。
  g_movePaused[motorIdx] = false;  // 更新全域狀態值。
  g_moveRemainingSteps[motorIdx] = 0;  // 更新全域狀態值。
  g_warmed[motorIdx] = false;  // 更新全域狀態值。
  releaseMotor(motorIdx);  // 執行此行控制邏輯。
}  // 程式區塊邊界。

static void handleStop(const String &arg) {  // 定義指令處理函式。
  int motor = 0;  // 設定變數值。
  bool hasMotor = false;  // 設定變數值。
  if (!parseOptionalMotor(arg, motor, hasMotor)) {  // 判斷條件是否成立。
    Serial.println(F("ERR STOP format"));  // 透過 Serial 輸出回覆。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  if (hasMotor) {  // 判斷條件是否成立。
    stopOneMotor((uint8_t)motor);  // 執行此行控制邏輯。
  } else {  // 程式區塊邊界。
    for (uint8_t motorIdx = 0; motorIdx < MOTOR_COUNT; motorIdx++) {  // 使用迴圈逐一處理。
      stopOneMotor(motorIdx);  // 執行此行控制邏輯。
    }  // 程式區塊邊界。
  }  // 程式區塊邊界。
  Serial.println(F("OK STOPPED"));  // 透過 Serial 輸出回覆。
}  // 程式區塊邊界。

static void handleCommand(const String &line) {  // 定義指令處理函式。
  String cmd = line;  // 設定變數值。
  cmd.trim();  // 移除字串前後空白。
  if (cmd.length() == 0) {  // 判斷條件是否成立。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  if (cmd.equalsIgnoreCase(F("PING"))) {  // 判斷條件是否成立。
    Serial.println(F("PONG"));  // 透過 Serial 輸出回覆。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  if (cmd.startsWith(F("MOVE"))) {  // 判斷條件是否成立。
    int sp = cmd.indexOf(' ');  // 拆解或轉換指令參數。
    if (sp < 0) {  // 判斷條件是否成立。
      Serial.println(F("ERR MOVE requires argument"));  // 透過 Serial 輸出回覆。
      return;  // 回傳結果或離開函式。
    }  // 程式區塊邊界。
    handleMove(cmd.substring(sp + 1));  // 拆解或轉換指令參數。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  if (cmd.startsWith(F("SPEED_MS"))) {  // 判斷條件是否成立。
    int sp = cmd.indexOf(' ');  // 拆解或轉換指令參數。
    if (sp < 0) {  // 判斷條件是否成立。
      Serial.println(F("ERR SPEED_MS requires argument"));  // 透過 Serial 輸出回覆。
      return;  // 回傳結果或離開函式。
    }  // 程式區塊邊界。
    handleSpeed(cmd.substring(sp + 1));  // 拆解或轉換指令參數。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  if (cmd.startsWith(F("DIR"))) {  // 判斷條件是否成立。
    int sp = cmd.indexOf(' ');  // 拆解或轉換指令參數。
    if (sp < 0) {  // 判斷條件是否成立。
      Serial.println(F("ERR DIR requires argument"));  // 透過 Serial 輸出回覆。
      return;  // 回傳結果或離開函式。
    }  // 程式區塊邊界。
    handleDir(cmd.substring(sp + 1));  // 拆解或轉換指令參數。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  if (cmd.startsWith(F("WARMUP_STEPS"))) {  // 判斷條件是否成立。
    int sp = cmd.indexOf(' ');  // 拆解或轉換指令參數。
    if (sp < 0) {  // 判斷條件是否成立。
      Serial.println(F("ERR WARMUP_STEPS requires argument"));  // 透過 Serial 輸出回覆。
      return;  // 回傳結果或離開函式。
    }  // 程式區塊邊界。
    handleWarmupSteps(cmd.substring(sp + 1));  // 拆解或轉換指令參數。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  if (cmd.startsWith(F("WARMUP_CYCLES"))) {  // 判斷條件是否成立。
    int sp = cmd.indexOf(' ');  // 拆解或轉換指令參數。
    if (sp < 0) {  // 判斷條件是否成立。
      Serial.println(F("ERR WARMUP_CYCLES requires argument"));  // 透過 Serial 輸出回覆。
      return;  // 回傳結果或離開函式。
    }  // 程式區塊邊界。
    handleWarmupCycles(cmd.substring(sp + 1));  // 拆解或轉換指令參數。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  if (cmd.startsWith(F("AUTOWARM"))) {  // 判斷條件是否成立。
    int sp = cmd.indexOf(' ');  // 拆解或轉換指令參數。
    if (sp < 0) {  // 判斷條件是否成立。
      Serial.println(F("ERR AUTOWARM requires argument"));  // 透過 Serial 輸出回覆。
      return;  // 回傳結果或離開函式。
    }  // 程式區塊邊界。
    handleAutoWarm(cmd.substring(sp + 1));  // 拆解或轉換指令參數。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  if (cmd.startsWith(F("WARMUP"))) {  // 判斷條件是否成立。
    int sp = cmd.indexOf(' ');  // 拆解或轉換指令參數。
    if (sp < 0) {  // 判斷條件是否成立。
      handleWarmup("");  // 執行此行控制邏輯。
      return;  // 回傳結果或離開函式。
    }  // 程式區塊邊界。
    handleWarmup(cmd.substring(sp + 1));  // 拆解或轉換指令參數。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  if (cmd.startsWith(F("HOLD"))) {  // 判斷條件是否成立。
    int sp = cmd.indexOf(' ');  // 拆解或轉換指令參數。
    if (sp < 0) {  // 判斷條件是否成立。
      handleHold("");  // 執行此行控制邏輯。
      return;  // 回傳結果或離開函式。
    }  // 程式區塊邊界。
    handleHold(cmd.substring(sp + 1));  // 拆解或轉換指令參數。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  if (cmd.startsWith(F("CALI"))) {  // 判斷條件是否成立。
    int sp = cmd.indexOf(' ');  // 拆解或轉換指令參數。
    if (sp < 0) {  // 判斷條件是否成立。
      handleCali("");  // 執行此行控制邏輯。
      return;  // 回傳結果或離開函式。
    }  // 程式區塊邊界。
    handleCali(cmd.substring(sp + 1));  // 拆解或轉換指令參數。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  if (cmd.startsWith(F("PAUSE"))) {  // 判斷條件是否成立。
    int sp = cmd.indexOf(' ');  // 拆解或轉換指令參數。
    if (sp < 0) {  // 判斷條件是否成立。
      handlePause("");  // 執行此行控制邏輯。
      return;  // 回傳結果或離開函式。
    }  // 程式區塊邊界。
    handlePause(cmd.substring(sp + 1));  // 拆解或轉換指令參數。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  if (cmd.startsWith(F("RESUME"))) {  // 判斷條件是否成立。
    int sp = cmd.indexOf(' ');  // 拆解或轉換指令參數。
    if (sp < 0) {  // 判斷條件是否成立。
      handleResume("");  // 執行此行控制邏輯。
      return;  // 回傳結果或離開函式。
    }  // 程式區塊邊界。
    handleResume(cmd.substring(sp + 1));  // 拆解或轉換指令參數。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  if (cmd.startsWith(F("STATUS"))) {  // 判斷條件是否成立。
    int sp = cmd.indexOf(' ');  // 拆解或轉換指令參數。
    if (sp < 0) {  // 判斷條件是否成立。
      handleStatus("");  // 執行此行控制邏輯。
      return;  // 回傳結果或離開函式。
    }  // 程式區塊邊界。
    handleStatus(cmd.substring(sp + 1));  // 拆解或轉換指令參數。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  if (cmd.startsWith(F("STOP"))) {  // 判斷條件是否成立。
    int sp = cmd.indexOf(' ');  // 拆解或轉換指令參數。
    if (sp < 0) {  // 判斷條件是否成立。
      handleStop("");  // 執行此行控制邏輯。
      return;  // 回傳結果或離開函式。
    }  // 程式區塊邊界。
    handleStop(cmd.substring(sp + 1));  // 拆解或轉換指令參數。
    return;  // 回傳結果或離開函式。
  }  // 程式區塊邊界。

  Serial.println(F("ERR unknown"));  // 透過 Serial 輸出回覆。
}  // 程式區塊邊界。

void setup() {  // Arduino 開機初始化。
  for (uint8_t motorIdx = 0; motorIdx < MOTOR_COUNT; motorIdx++) {  // 使用迴圈逐一處理。
    for (uint8_t pinIdx = 0; pinIdx < MOTOR_PIN_COUNT; pinIdx++) {  // 使用迴圈逐一處理。
      pinMode(MOTOR_PIN[motorIdx][pinIdx], OUTPUT);  // 設定 Arduino 腳位為輸出模式。
    }  // 程式區塊邊界。

    releaseMotor(motorIdx);  // 執行此行控制邏輯。
    g_phaseIdx[motorIdx] = 0;  // 更新全域狀態值。
    g_stepDelayMs[motorIdx] = DEFAULT_STEP_DELAY_MS;  // 更新全域狀態值。
    g_warmupSteps[motorIdx] = DEFAULT_WARMUP_STEPS;  // 更新全域狀態值。
    g_warmupCycles[motorIdx] = DEFAULT_WARMUP_CYCLES;  // 更新全域狀態值。
    g_dirSign[motorIdx] = 1;  // 更新全域狀態值。
    g_holdEnabled[motorIdx] = true;  // 更新全域狀態值。
    g_autoWarmupEnabled[motorIdx] = true;  // 更新全域狀態值。
    g_warmed[motorIdx] = false;  // 更新全域狀態值。
  }  // 程式區塊邊界。

  Serial.begin(115200);  // 透過 Serial 輸出回覆。
  delay(300);  // 短暫等待讓動作穩定。
  Serial.println(F("READY XY"));  // 透過 Serial 輸出回覆。
}  // 程式區塊邊界。

void loop() {  // Arduino 主迴圈。
  while (Serial.available() > 0) {  // 持續讀取可用資料。
    char c = (char)Serial.read();  // 讀取 Serial 資料。
    if (c == '\n') {  // 判斷條件是否成立。
      handleCommand(g_line);  // 執行此行控制邏輯。
      g_line = "";  // 更新全域狀態值。
    } else if (c != '\r') {  // 設定變數值。
      g_line += c;  // 更新全域狀態值。
      if (g_line.length() > 128) {  // 判斷條件是否成立。
        g_line = "";  // 更新全域狀態值。
      }  // 程式區塊邊界。
    }  // 程式區塊邊界。
  }  // 程式區塊邊界。

  serviceAllMotors();  // 執行此行控制邏輯。
}  // 程式區塊邊界。
