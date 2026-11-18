// Arduino 28BYJ-48 + ULN2003 X 軸馬達序列埠控制器
// 單軸版本：這一片 Arduino 只控制一顆 X 軸步進馬達。
//
// 接線方式：
//   IN1 -> D4
//   IN2 -> D5
//   IN3 -> D6
//   IN4 -> D7
//
// 通訊協定：每一行指令都要用換行結尾。
//   PING                    // 測試 Arduino 是否有回應
//   MOVE <steps>            // 相對移動指定步數，可用負數反轉方向
//   SPEED_MS <ms>           // 設定每半步間隔，範圍 1..250 ms
//   DIR <-1|1>              // 設定整體方向倍率
//   WARMUP [steps] [cycles] // 暖機，預設 80 步、1 次來回
//   AUTOWARM <0|1>          // 是否在第一次 MOVE 前自動暖機
//   WARMUP_STEPS <steps>    // 設定預設暖機步數，範圍 1..80
//   WARMUP_CYCLES <n>       // 設定預設暖機次數，範圍 0..10
//   HOLD <0|1>              // 移動後是否保持線圈通電
//   CALI [steps]            // 校正測試：先正轉再反轉
//   PAUSE                   // 暫停目前移動
//   RESUME                  // 繼續暫停中的移動
//   STATUS                  // 回報目前狀態與步數進度
//   STOP                    // 停止並釋放馬達
//
// 回覆格式：
//   READY X-motor           // 開機完成
//   PONG                    // PING 的回覆
//   OK                      // 指令成功
//   DONE <steps>            // MOVE 完成
//   ERR ...                 // 指令錯誤

// 載入 Arduino 核心函式，例如 pinMode、digitalWrite、Serial、millis。
#include <Arduino.h>

// 馬達名稱，用於 READY、WARMUP、CALI 等序列埠回覆。
const char kMotorName[] = "X-motor";
// ULN2003 四個輸入腳位，依序接到 Arduino D4、D5、D6、D7。
const uint8_t kMotorPins[4] = {4, 5, 6, 7};
// 預設每一步的延遲時間，數字越小速度越快。
const uint8_t kDefaultStepDelayMs = 5;
// 允許的最快步進延遲，避免速度太快導致馬達失步。
const uint8_t kMinStepDelayMs = 1;
// 允許的最慢步進延遲，避免使用者輸入過大數值。
const uint8_t kMaxStepDelayMs = 250;
// 預設暖機步數。
const uint8_t kDefaultWarmupSteps = 80;
// 預設暖機來回次數。
const uint8_t kDefaultWarmupCycles = 1;
// 暖機步數上限，避免暖機跑太遠。
const uint8_t kMaxWarmupSteps = 80;
// 暖機次數上限，避免一次指令拖太久。
const uint8_t kMaxWarmupCycles = 10;
// 暖機時最低延遲，讓暖機速度不要太快。
const uint8_t kWarmupMinDelayMs = 8;

// 28BYJ-48 半步進相序，共 8 個狀態。
// 每列代表 IN1、IN2、IN3、IN4 是否通電。
const uint8_t SEQ[8][4] = {
  {1, 0, 0, 0}, // 第 0 相
  {1, 1, 0, 0}, // 第 1 相
  {0, 1, 0, 0}, // 第 2 相
  {0, 1, 1, 0}, // 第 3 相
  {0, 0, 1, 0}, // 第 4 相
  {0, 0, 1, 1}, // 第 5 相
  {0, 0, 0, 1}, // 第 6 相
  {1, 0, 0, 1}, // 第 7 相
};

// 目前所在的相序索引，範圍 0..7。
int8_t g_phaseIdx = 0;
// 目前每一步的延遲時間。
uint8_t g_stepDelayMs = kDefaultStepDelayMs;
// 目前預設暖機步數。
uint8_t g_warmupSteps = kDefaultWarmupSteps;
// 目前預設暖機次數。
uint8_t g_warmupCycles = kDefaultWarmupCycles;
// 方向倍率，1 表示正常方向，-1 表示反向。
int8_t g_dirSign = 1;
// 是否在移動後保持線圈通電。
bool g_holdEnabled = true;
// 是否在第一次移動前自動暖機。
bool g_autoWarmupEnabled = true;
// 是否已經完成暖機。
bool g_warmed = false;
// 累積序列埠收到的一整行指令。
String g_line;
// 是否正在執行 MOVE。
bool g_moveActive = false;
// MOVE 是否被 PAUSE 暫停。
bool g_movePaused = false;
// 使用者原本要求的步數，保留正負方向。
long g_moveRequestedSteps = 0;
// 已經執行的步數，永遠用正數累計。
long g_moveExecutedSteps = 0;
// 剩餘尚未執行的步數。
long g_moveRemainingSteps = 0;
// 本次 MOVE 實際使用的方向，已經包含 DIR 倍率。
int8_t g_moveDirection = 1;
// 下一次允許步進的時間點，用 millis() 計算。
unsigned long g_nextStepAtMs = 0;

// 解析常見的步數或數值參數。
// allowNoArg=true 時，允許沒有參數，由呼叫端使用預設值。
static bool parseStepsArg(const String &arg, long &steps, bool allowNoArg) {
  // 複製一份字串，避免直接修改傳入參數。
  String t = arg;
  // 移除前後空白。
  t.trim();

  // 沒有輸入參數時，依 allowNoArg 決定是否接受。
  if (t.length() == 0) {
    return allowNoArg ? true : false;
  }
  // 若允許省略參數，先放入常用預設步數。
  if (allowNoArg) {
    steps = 80;
  }

  // 找第一個空白，用來判斷是否有兩段參數。
  int sp = t.indexOf(' ');
  // 只有一段參數時，直接轉成數字。
  if (sp < 0) {
    steps = t.toInt();
    return true;
  }

  // 拆出第一段與第二段。
  String first = t.substring(0, sp);
  String second = t.substring(sp + 1);
  // 清掉拆分後可能留下的空白。
  first.trim();
  second.trim();

  // 相容雙軸格式：如果第一段是 0 或 1，就把第二段當真正數值。
  if ((first == "0" || first == "1") && second.length() > 0) {
    steps = second.toInt();
    return true;
  }

  // 其他格式視為錯誤。
  return false;
}

// 將指定相序輸出到四個馬達控制腳位。
static void applyPhase(uint8_t phase) {
  // phase 只保留 0..7，避免陣列索引超出範圍。
  phase &= 7;
  // 依半步相序控制 IN1。
  digitalWrite(kMotorPins[0], SEQ[phase][0] ? HIGH : LOW);
  // 依半步相序控制 IN2。
  digitalWrite(kMotorPins[1], SEQ[phase][1] ? HIGH : LOW);
  // 依半步相序控制 IN3。
  digitalWrite(kMotorPins[2], SEQ[phase][2] ? HIGH : LOW);
  // 依半步相序控制 IN4。
  digitalWrite(kMotorPins[3], SEQ[phase][3] ? HIGH : LOW);
}

// 關閉四個線圈，讓馬達釋放不保持。
static void releaseMotor() {
  // 關閉 IN1。
  digitalWrite(kMotorPins[0], LOW);
  // 關閉 IN2。
  digitalWrite(kMotorPins[1], LOW);
  // 關閉 IN3。
  digitalWrite(kMotorPins[2], LOW);
  // 關閉 IN4。
  digitalWrite(kMotorPins[3], LOW);
}

// 執行一個半步，dir=1 正向，dir=-1 反向。
static void applyStep(int8_t dir) {
  // 先用較大的型別計算，方便處理 -1。
  int16_t nextPhase = (int16_t)g_phaseIdx + dir;
  // 相序小於 0 時繞回第 7 相。
  if (nextPhase < 0) nextPhase = 7;
  // 相序大於 7 時繞回第 0 相。
  else if (nextPhase > 7) nextPhase = 0;
  // 更新目前相序。
  g_phaseIdx = (int8_t)nextPhase;

  // 實際輸出新的相序。
  applyPhase((uint8_t)g_phaseIdx);
}

// 阻塞式單步，主要給暖機與校正使用。
static void stepRaw(int8_t dir) {
  // 先走一步。
  applyStep(dir);
  // 等待目前設定的步進延遲。
  delay(g_stepDelayMs);
}

// 阻塞式移動指定步數，主要給暖機與校正使用。
static void moveRaw(long steps) {
  // 0 步不用動。
  if (steps == 0) return;

  // 取絕對值作為迴圈次數。
  long n = steps;
  if (n < 0) n = -n;
  // 由正負號決定方向。
  int8_t dir = (steps > 0) ? 1 : -1;
  // 套用使用者設定的 DIR 方向倍率。
  dir *= g_dirSign;

  // 逐步輸出相序。
  for (long i = 0; i < n; i++) {
    stepRaw(dir);
  }
}

// 執行暖機：小幅正轉再反轉，讓齒輪與機構先進入穩定狀態。
static void runWarmup(uint8_t steps, uint8_t cycles) {
  // 暖機步數至少 1。
  if (steps < 1) steps = 1;
  // 暖機步數不可超過上限。
  if (steps > kMaxWarmupSteps) steps = kMaxWarmupSteps;
  // 暖機次數不可超過上限。
  if (cycles > kMaxWarmupCycles) cycles = kMaxWarmupCycles;
  // cycles=0 表示略過暖機，但標記為已暖機。
  if (cycles == 0) {
    g_warmed = true;
    return;
  }

  // 保存原本速度，暖機結束後要還原。
  uint8_t prevDelay = g_stepDelayMs;
  // 暖機速度太快時，自動改成較慢的最低暖機速度。
  if (g_stepDelayMs < kWarmupMinDelayMs) {
    g_stepDelayMs = kWarmupMinDelayMs;
  }

  // 依指定次數做正轉與反轉。
  for (uint8_t i = 0; i < cycles; i++) {
    // 暖機正向移動。
    moveRaw(steps);
    // 短暫等待，讓機構穩定。
    delay(20);
    // 暖機反向回來。
    moveRaw(-steps);
    // 短暫等待，讓機構穩定。
    delay(20);
  }

  // 還原暖機前的速度。
  g_stepDelayMs = prevDelay;
  // 如果沒有啟用 HOLD，暖機後釋放馬達。
  if (!g_holdEnabled) {
    releaseMotor();
  }
  // 標記已暖機。
  g_warmed = true;
}

// 結束目前非阻塞 MOVE，並回報 DONE。
static void finishActiveMove() {
  // 保留原始要求步數，回覆給上位機。
  long completedSteps = g_moveRequestedSteps;
  // 清除移動狀態。
  g_moveActive = false;
  // 清除暫停狀態。
  g_movePaused = false;
  // 剩餘步數歸零。
  g_moveRemainingSteps = 0;
  // 若不保持通電，完成後釋放馬達。
  if (!g_holdEnabled) {
    releaseMotor();
  }
  // 回覆完成訊息。
  Serial.print(F("DONE "));
  Serial.println(completedSteps);
}

// 在 loop() 中反覆呼叫，負責非阻塞地執行 MOVE。
static void serviceActiveMove() {
  // 沒有移動或已暫停時，不做任何事。
  if (!g_moveActive || g_movePaused) return;
  // 取得目前時間。
  unsigned long now = millis();
  // 還沒到下一步時間時，先返回。
  if ((long)(now - g_nextStepAtMs) < 0) return;

  // 到時間就走一步。
  applyStep(g_moveDirection);
  // 已執行步數加一。
  g_moveExecutedSteps++;
  // 剩餘步數減一。
  g_moveRemainingSteps--;
  // 剩餘步數用完就結束 MOVE。
  if (g_moveRemainingSteps <= 0) {
    finishActiveMove();
    return;
  }
  // 設定下一步的時間點。
  g_nextStepAtMs = now + g_stepDelayMs;
}

// 啟動一個非阻塞 MOVE。
static void moveSteps(long steps) {
  // 0 步直接回報完成。
  if (steps == 0) {
    Serial.println(F("DONE 0"));
    return;
  }
  // 同時間只允許一個 MOVE。
  if (g_moveActive) {
    Serial.println(F("ERR BUSY"));
    return;
  }

  // 如果啟用自動暖機且尚未暖機，就先暖機。
  if (g_autoWarmupEnabled && !g_warmed) {
    runWarmup(g_warmupSteps, g_warmupCycles);
  }

  // 記錄原始要求步數。
  g_moveRequestedSteps = steps;
  // 重設已執行步數。
  g_moveExecutedSteps = 0;
  // 剩餘步數使用絕對值。
  g_moveRemainingSteps = (steps < 0) ? -steps : steps;
  // 依步數正負決定方向。
  g_moveDirection = (steps > 0) ? 1 : -1;
  // 套用 DIR 方向倍率。
  g_moveDirection *= g_dirSign;
  // MOVE 一開始不是暫停狀態。
  g_movePaused = false;
  // 標記 MOVE 啟動。
  g_moveActive = true;
  // 讓下一輪 loop() 可以立即開始第一步。
  g_nextStepAtMs = millis();
}

// 處理 MOVE 指令。
static void handleMove(const String &arg) {
  // 存放解析後的步數。
  long steps = 0;
  // MOVE 必須有步數參數。
  if (!parseStepsArg(arg, steps, false)) {
    Serial.println(F("ERR MOVE format"));
    return;
  }
  // 啟動非阻塞移動。
  moveSteps(steps);
}

// 處理 SPEED_MS 指令。
static void handleSpeed(const String &arg) {
  // 預設速度值。
  long ms = kDefaultStepDelayMs;
  // SPEED_MS 必須有數值參數。
  if (!parseStepsArg(arg, ms, false)) {
    Serial.println(F("ERR SPEED_MS format"));
    return;
  }
  // 限制最小延遲。
  if (ms < kMinStepDelayMs) ms = kMinStepDelayMs;
  // 限制最大延遲。
  if (ms > kMaxStepDelayMs) ms = kMaxStepDelayMs;
  // 更新目前速度。
  g_stepDelayMs = (uint8_t)ms;
  // 回覆成功。
  Serial.println(F("OK"));
}

// 處理 DIR 指令。
static void handleDir(const String &arg) {
  // 複製參數字串。
  String t = arg;
  // 去除前後空白。
  t.trim();
  // DIR 必須有方向參數。
  if (t.length() == 0) {
    Serial.println(F("ERR DIR format"));
    return;
  }

  // 檢查是否是雙軸格式，例如 DIR 0 -1。
  int sp = t.indexOf(' ');
  if (sp >= 0) {
    // 拆出可能的軸編號。
    String first = t.substring(0, sp);
    // 拆出真正方向值。
    String second = t.substring(sp + 1);
    // 清除空白。
    first.trim();
    second.trim();
    // 若第一段是軸編號，使用第二段當方向值。
    if ((first == "0" || first == "1") && second.length() > 0) {
      t = second;
    } else {
      // 不是可接受格式就回報錯誤。
      Serial.println(F("ERR DIR format"));
      return;
    }
  }

  // 轉成整數，>=0 視為正向，<0 視為反向。
  int sign = t.toInt();
  // 儲存方向倍率。
  g_dirSign = (sign >= 0) ? 1 : -1;
  // 方向改變後，讓下次移動重新暖機。
  g_warmed = false;
  // 回覆成功。
  Serial.println(F("OK"));
}

// 處理 WARMUP 指令。
static void handleWarmup(const String &arg) {
  // 複製參數。
  String t = arg;
  // 去除空白。
  t.trim();
  // 支援雙軸格式：如果前面帶 0 或 1，會忽略軸編號。
  int firstSp = t.indexOf(' ');
  if (firstSp >= 0) {
    // 拆出第一段。
    String first = t.substring(0, firstSp);
    // 拆出剩下參數。
    String rest = t.substring(firstSp + 1);
    // 清除空白。
    first.trim();
    rest.trim();
    // 若第一段是軸編號，就只保留後面參數。
    if ((first == "0" || first == "1") && rest.length() > 0) {
      t = rest;
    }
  }
  // 預設使用目前設定的暖機步數。
  long steps = g_warmupSteps;
  // 預設使用目前設定的暖機次數。
  long cycles = g_warmupCycles;

  // 如果有輸入參數，就解析 steps 或 steps cycles。
  if (t.length() > 0) {
    // 找第一個空白分隔。
    int sp = t.indexOf(' ');
    // 只有一個參數時，代表 steps。
    if (sp < 0) {
      steps = t.toInt();
    } else {
      // 兩個參數時，第一個是 steps，第二個是 cycles。
      String first = t.substring(0, sp);
      String second = t.substring(sp + 1);
      // 清掉前後空白。
      first.trim();
      second.trim();
      // 解析暖機步數。
      steps = first.toInt();
      // 如果第二段不空，解析暖機次數。
      if (second.length() > 0) {
        cycles = second.toInt();
      }
    }
  }

  // 暖機步數至少 1。
  if (steps < 1) steps = 1;
  // 暖機步數限制在上限內。
  if (steps > kMaxWarmupSteps) steps = kMaxWarmupSteps;
  // 暖機次數不可小於 0。
  if (cycles < 0) cycles = 0;
  // 暖機次數限制在上限內。
  if (cycles > kMaxWarmupCycles) cycles = kMaxWarmupCycles;

  // 回報即將執行暖機的設定。
  Serial.print(F("WARMUP "));
  Serial.print(kMotorName);
  Serial.print(F(" steps="));
  Serial.print(steps);
  Serial.print(F(" cycles="));
  Serial.println(cycles);
  // 執行暖機。
  runWarmup((uint8_t)steps, (uint8_t)cycles);
  // 回覆成功。
  Serial.println(F("OK"));
}

// 處理 AUTOWARM 指令。
static void handleAutoWarm(const String &arg) {
  // 預設啟用自動暖機。
  long enabled = 1;
  // 必須能解析 0 或 1。
  if (!parseStepsArg(arg, enabled, false)) {
    Serial.println(F("ERR AUTOWARM format"));
    return;
  }
  // 非 0 代表啟用，0 代表停用。
  g_autoWarmupEnabled = (enabled != 0);
  // 停用自動暖機時，直接視為已暖機。
  if (!g_autoWarmupEnabled) {
    g_warmed = true;
  }
  // 回覆成功。
  Serial.println(F("OK"));
}

// 處理 WARMUP_STEPS 指令。
static void handleWarmupSteps(const String &arg) {
  // 預設暖機步數。
  long steps = kDefaultWarmupSteps;
  // 必須能解析步數。
  if (!parseStepsArg(arg, steps, false)) {
    Serial.println(F("ERR WARMUP_STEPS format"));
    return;
  }
  // 限制最小值。
  if (steps < 1) steps = 1;
  // 限制最大值。
  if (steps > kMaxWarmupSteps) steps = kMaxWarmupSteps;
  // 更新預設暖機步數。
  g_warmupSteps = (uint8_t)steps;
  // 設定改變後，下次移動重新暖機。
  g_warmed = false;
  // 回覆成功。
  Serial.println(F("OK"));
}

// 處理 WARMUP_CYCLES 指令。
static void handleWarmupCycles(const String &arg) {
  // 預設暖機次數。
  long cycles = kDefaultWarmupCycles;
  // 必須能解析次數。
  if (!parseStepsArg(arg, cycles, false)) {
    Serial.println(F("ERR WARMUP_CYCLES format"));
    return;
  }
  // 次數不可小於 0。
  if (cycles < 0) cycles = 0;
  // 次數不可超過上限。
  if (cycles > kMaxWarmupCycles) cycles = kMaxWarmupCycles;
  // 更新預設暖機次數。
  g_warmupCycles = (uint8_t)cycles;
  // 設定改變後，下次移動重新暖機。
  g_warmed = false;
  // 回覆成功。
  Serial.println(F("OK"));
}

// 處理 HOLD 指令。
static void handleHold(const String &arg) {
  // 預設啟用 HOLD。
  long enabled = 1;
  // 必須能解析 0 或 1。
  if (!parseStepsArg(arg, enabled, false)) {
    Serial.println(F("ERR HOLD format"));
    return;
  }
  // 非 0 代表保持通電。
  g_holdEnabled = (enabled != 0);
  // 關閉 HOLD 時，立刻釋放馬達。
  if (!g_holdEnabled) {
    releaseMotor();
  } else {
    // 開啟 HOLD 時，輸出目前相序保持位置。
    applyPhase((uint8_t)g_phaseIdx);
  }
  // 回覆成功。
  Serial.println(F("OK"));
}

// 處理 CALI 校正測試指令。
static void handleCali(const String &arg) {
  // 移動中不允許校正，避免狀態衝突。
  if (g_moveActive) {
    Serial.println(F("ERR BUSY"));
    return;
  }
  // 預設校正步數。
  long steps = 80;
  // CALI 可省略步數。
  if (!parseStepsArg(arg, steps, true)) {
    Serial.println(F("ERR CALI format"));
    return;
  }

  // 非正數時改回預設值。
  if (steps <= 0) steps = 80;
  // 限制校正最大步數，避免跑太遠。
  if (steps > 20000) steps = 20000;

  // 保存原本速度。
  uint8_t prevDelay = g_stepDelayMs;
  // 校正時速度太快就放慢到 12 ms。
  if (g_stepDelayMs < 12) g_stepDelayMs = 12;

  // 回報校正資訊。
  Serial.print(F("CALI "));
  Serial.print(F("X-motor "));
  Serial.println(steps);

  // 先正向移動。
  moveRaw(steps);
  // 再反向移回。
  moveRaw(-steps);
  // 若不保持通電，校正後釋放馬達。
  if (!g_holdEnabled) {
    releaseMotor();
  }
  // 還原校正前速度。
  g_stepDelayMs = prevDelay;
  // 回覆成功。
  Serial.println(F("OK"));
}

// 處理 PAUSE 指令。
static void handlePause() {
  // 有移動中的 MOVE 才進入暫停。
  if (g_moveActive) {
    g_movePaused = true;
    Serial.println(F("OK PAUSED"));
  } else {
    // 沒有移動時，回報目前閒置。
    Serial.println(F("OK IDLE"));
  }
}

// 處理 RESUME 指令。
static void handleResume() {
  // 移動中且已暫停時，恢復移動。
  if (g_moveActive && g_movePaused) {
    g_movePaused = false;
    g_nextStepAtMs = millis();
    Serial.println(F("OK RUNNING"));
  } else if (g_moveActive) {
    // 已經在移動時，直接回報 RUNNING。
    Serial.println(F("OK RUNNING"));
  } else {
    // 沒有移動時，回報 IDLE。
    Serial.println(F("OK IDLE"));
  }
}

// 處理 STATUS 指令。
static void handleStatus() {
  // 回覆狀態開頭。
  Serial.print(F("STATUS "));
  // 沒有移動時回報 IDLE。
  if (!g_moveActive) {
    Serial.print(F("IDLE "));
  } else if (g_movePaused) {
    // 暫停中回報 PAUSED。
    Serial.print(F("PAUSED "));
  } else {
    // 正在移動時回報 RUNNING。
    Serial.print(F("RUNNING "));
  }
  // 輸出要求步數。
  Serial.print(g_moveRequestedSteps);
  Serial.print(F(" "));
  // 輸出已執行步數。
  Serial.print(g_moveExecutedSteps);
  Serial.print(F(" "));
  // 輸出剩餘步數。
  Serial.println(g_moveRemainingSteps);
}

// 處理 STOP 指令。
static void handleStop() {
  // 停止目前 MOVE。
  g_moveActive = false;
  // 清除暫停狀態。
  g_movePaused = false;
  // 剩餘步數歸零。
  g_moveRemainingSteps = 0;
  // 釋放馬達線圈。
  releaseMotor();
  // 下次移動前需要重新暖機。
  g_warmed = false;
  // 回覆停止完成。
  Serial.println(F("OK STOPPED"));
}

// 解析並分派一整行序列埠指令。
static void handleCommand(const String &line) {
  // 複製輸入字串。
  String cmd = line;
  // 去除前後空白。
  cmd.trim();
  // 空行直接忽略。
  if (cmd.length() == 0) return;

  // PING 用來測試連線。
  if (cmd.equalsIgnoreCase(F("PING"))) {
    Serial.println(F("PONG"));
    return;
  }
  // MOVE 指令：相對移動指定步數。
  if (cmd.startsWith(F("MOVE"))) {
    // 找出指令和參數之間的空白。
    int sp = cmd.indexOf(' ');
    // 沒有參數就回報錯誤。
    if (sp < 0) {
      Serial.println(F("ERR MOVE requires argument"));
      return;
    }
    // 把參數交給 MOVE 處理函式。
    handleMove(cmd.substring(sp + 1));
    return;
  }
  // SPEED_MS 指令：設定每步延遲。
  if (cmd.startsWith(F("SPEED_MS"))) {
    // 找出參數位置。
    int sp = cmd.indexOf(' ');
    // 沒有參數就回報錯誤。
    if (sp < 0) {
      Serial.println(F("ERR SPEED_MS requires argument"));
      return;
    }
    // 處理速度參數。
    handleSpeed(cmd.substring(sp + 1));
    return;
  }
  // DIR 指令：設定方向倍率。
  if (cmd.startsWith(F("DIR"))) {
    // 找出參數位置。
    int sp = cmd.indexOf(' ');
    // 沒有參數就回報錯誤。
    if (sp < 0) {
      Serial.println(F("ERR DIR requires argument"));
      return;
    }
    // 處理方向參數。
    handleDir(cmd.substring(sp + 1));
    return;
  }
  // WARMUP_STEPS 指令：設定預設暖機步數。
  if (cmd.startsWith(F("WARMUP_STEPS"))) {
    // 找出參數位置。
    int sp = cmd.indexOf(' ');
    // 沒有參數就回報錯誤。
    if (sp < 0) {
      Serial.println(F("ERR WARMUP_STEPS requires argument"));
      return;
    }
    // 處理暖機步數設定。
    handleWarmupSteps(cmd.substring(sp + 1));
    return;
  }
  // WARMUP_CYCLES 指令：設定預設暖機次數。
  if (cmd.startsWith(F("WARMUP_CYCLES"))) {
    // 找出參數位置。
    int sp = cmd.indexOf(' ');
    // 沒有參數就回報錯誤。
    if (sp < 0) {
      Serial.println(F("ERR WARMUP_CYCLES requires argument"));
      return;
    }
    // 處理暖機次數設定。
    handleWarmupCycles(cmd.substring(sp + 1));
    return;
  }
  // AUTOWARM 指令：開關自動暖機。
  if (cmd.startsWith(F("AUTOWARM"))) {
    // 找出參數位置。
    int sp = cmd.indexOf(' ');
    // 沒有參數就回報錯誤。
    if (sp < 0) {
      Serial.println(F("ERR AUTOWARM requires argument"));
      return;
    }
    // 處理自動暖機設定。
    handleAutoWarm(cmd.substring(sp + 1));
    return;
  }
  // WARMUP 指令：立即執行暖機。
  if (cmd.startsWith(F("WARMUP"))) {
    // 檢查是否有參數。
    int sp = cmd.indexOf(' ');
    // 沒有參數時使用預設暖機設定。
    if (sp < 0) {
      handleWarmup("");
      return;
    }
    // 有參數時用參數指定步數與次數。
    handleWarmup(cmd.substring(sp + 1));
    return;
  }
  // HOLD 指令：設定是否保持通電。
  if (cmd.startsWith(F("HOLD"))) {
    // 檢查是否有參數。
    int sp = cmd.indexOf(' ');
    // 沒有參數時預設開啟 HOLD。
    if (sp < 0) {
      handleHold("1");
      return;
    }
    // 有參數時依參數設定 HOLD。
    handleHold(cmd.substring(sp + 1));
    return;
  }
  // CALI 指令：正反向移動做校正測試。
  if (cmd.startsWith(F("CALI"))) {
    // 檢查是否有參數。
    int sp = cmd.indexOf(' ');
    // 沒有參數時使用預設校正步數。
    if (sp < 0) {
      handleCali("");
      return;
    }
    // 有參數時依指定步數校正。
    handleCali(cmd.substring(sp + 1));
    return;
  }
  // PAUSE 指令：暫停目前 MOVE。
  if (cmd.equalsIgnoreCase(F("PAUSE"))) {
    handlePause();
    return;
  }
  // RESUME 指令：恢復目前 MOVE。
  if (cmd.equalsIgnoreCase(F("RESUME"))) {
    handleResume();
    return;
  }
  // STATUS 指令：回報目前狀態。
  if (cmd.equalsIgnoreCase(F("STATUS"))) {
    handleStatus();
    return;
  }
  // STOP 指令：停止並釋放馬達。
  if (cmd.equalsIgnoreCase(F("STOP"))) {
    handleStop();
    return;
  }
  // 找不到對應指令時回報未知指令。
  Serial.println(F("ERR unknown"));
}

// Arduino 開機後只執行一次。
void setup() {
  // 設定四個馬達控制腳位為輸出。
  for (uint8_t i = 0; i < 4; i++) {
    pinMode(kMotorPins[i], OUTPUT);
  }
  // 開機先關閉線圈，避免馬達誤動或發熱。
  releaseMotor();
  // 初始相序設為 0。
  g_phaseIdx = 0;
  // 還原預設速度。
  g_stepDelayMs = kDefaultStepDelayMs;
  // 還原預設暖機步數。
  g_warmupSteps = kDefaultWarmupSteps;
  // 還原預設暖機次數。
  g_warmupCycles = kDefaultWarmupCycles;
  // 預設方向為正向。
  g_dirSign = 1;
  // 預設移動後保持通電。
  g_holdEnabled = true;
  // 預設啟用第一次移動前自動暖機。
  g_autoWarmupEnabled = true;
  // 開機時尚未暖機。
  g_warmed = false;

  // 啟動序列埠，鮑率 115200。
  Serial.begin(115200);
  // 等待序列埠穩定。
  delay(300);
  // 告知上位機 Arduino 已準備完成。
  Serial.print(F("READY "));
  Serial.println(kMotorName);
}

// Arduino 主迴圈會一直重複執行。
void loop() {
  // 讀取序列埠所有可用字元。
  while (Serial.available() > 0) {
    // 讀取一個字元。
    char c = (char)Serial.read();
    // 收到換行代表一整行指令結束。
    if (c == '\n') {
      // 處理累積好的指令。
      handleCommand(g_line);
      // 清空緩衝，準備下一行。
      g_line = "";
    } else if (c != '\r') {
      // 忽略 carriage return，只累積一般字元。
      g_line += c;
      // 指令太長時清空，避免 String 無限制變大。
      if (g_line.length() > 96) {
        g_line = "";
      }
    }
  }
  // 每輪都服務非阻塞移動，讓 MOVE 可以一邊跑一邊收指令。
  serviceActiveMove();
}
