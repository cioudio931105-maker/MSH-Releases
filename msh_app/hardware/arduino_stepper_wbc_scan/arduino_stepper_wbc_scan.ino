// Arduino Stepper Controller for WBC serpentine scan (STEP/DIR driver: A4988 / DRV8825)
// Upload this same sketch to both Arduino boards.
// Each board controls one axis through Motor 0:
//   STEP -> D2
//   DIR  -> D3
//   EN   -> D8 (optional, active LOW)
//
// Commands over Serial (newline-terminated):
//   PING
//   MOVE <steps>               (legacy, default motor 0, e.g. MOVE 200, MOVE -200)
//   MOVE <motor> <steps>       (motor optional, 0 or 1, e.g. MOVE 1 200, MOVE 0 -200)
//   SPEED_MS <milliseconds>          (legacy, motor 0)
//   SPEED_MS <motor> <milliseconds>  (motor optional, 0 or 1)
//   SPEED_US <microseconds>           (optional fine-grained control, motor 0)
//   STOP                       (interrupt the active move)
//   ENABLE <0|1>
// Replies:
//   PONG
//   OK
//   DONE <steps>

const int PIN_STEP[2] = {2, 4};
const int PIN_DIR[2] = {3, 5};
const int PIN_EN = 8;

// Delay between STEP edges. Increase this value if the platform skips steps.
volatile unsigned int stepDelayUs[2] = {800, 800};

bool driverEnabled = true;
bool stopRequested = false;
String line;
String moveLine;

static bool parseMotor(const String &s, int &motorIdx) {
  String t = s;
  t.trim();
  if (t.length() != 1) {
    return false;
  }
  char c = t.charAt(0);
  if (c != '0' && c != '1') {
    return false;
  }
  motorIdx = c - '0';
  return true;
}

static bool parseMotorOrDefault(const String &arg, int &motorIdx, long &steps) {
  int sp = arg.indexOf(' ');
  if (sp < 0) {
    motorIdx = 0;
    steps = arg.toInt();
    return true;
  }

  String first = arg.substring(0, sp);
  String second = arg.substring(sp + 1);
  first.trim();
  second.trim();
  if (!parseMotor(first, motorIdx) || second.length() == 0) {
    return false;
  }
  steps = second.toInt();
  return true;
}

static void setEnabled(bool enabled) {
  driverEnabled = enabled;
  digitalWrite(PIN_EN, enabled ? LOW : HIGH);
}

static void stepOnce(int motorIdx) {
  if (motorIdx < 0 || motorIdx > 1) {
    return;
  }
  digitalWrite(PIN_STEP[motorIdx], HIGH);
  delayMicroseconds(stepDelayUs[motorIdx]);
  digitalWrite(PIN_STEP[motorIdx], LOW);
  delayMicroseconds(stepDelayUs[motorIdx]);
}

static void pollStopDuringMove() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n') {
      moveLine.trim();
      if (moveLine.equalsIgnoreCase("STOP") || moveLine.startsWith("STOP ")) {
        stopRequested = true;
        Serial.println("OK STOP");
      } else if (moveLine.length() > 0) {
        Serial.println("ERR busy");
      }
      moveLine = "";
    } else if (c != '\r') {
      moveLine += c;
      if (moveLine.length() > 128) {
        moveLine = "";
      }
    }
  }
}

static void moveSteps(int motorIdx, long steps) {
  if (motorIdx < 0 || motorIdx > 1) {
    Serial.println("ERR invalid motor");
    return;
  }
  if (steps == 0) {
    Serial.println("DONE 0");
    return;
  }

  if (!driverEnabled) {
    setEnabled(true);
  }

  if (steps > 0) {
    digitalWrite(PIN_DIR[motorIdx], HIGH);
  } else {
    digitalWrite(PIN_DIR[motorIdx], LOW);
    steps = -steps;
  }

  stopRequested = false;
  long completedSteps = 0;
  for (long i = 0; i < steps; i++) {
    pollStopDuringMove();
    if (stopRequested) {
      break;
    }
    stepOnce(motorIdx);
    completedSteps++;
  }

  Serial.print("DONE ");
  Serial.println(completedSteps);
}

static void handleCommand(const String &cmdLine) {
  String cmd = cmdLine;
  cmd.trim();
  if (cmd.length() == 0) return;

  if (cmd.equalsIgnoreCase("PING")) {
    Serial.println("PONG");
    return;
  }

  if (cmd.equalsIgnoreCase("STOP") || cmd.startsWith("STOP ")) {
    stopRequested = true;
    Serial.println("OK STOP");
    return;
  }

  if (cmd.startsWith("MOVE")) {
    int sp = cmd.indexOf(' ');
    if (sp < 0) {
      Serial.println("ERR MOVE requires argument");
      return;
    }
    int motorIdx = 0;
    long steps = 0;
    if (!parseMotorOrDefault(cmd.substring(sp + 1), motorIdx, steps)) {
      Serial.println("ERR MOVE format");
      return;
    }
    moveSteps(motorIdx, steps);
    return;
  }

  if (cmd.startsWith("SPEED_MS")) {
    int sp = cmd.indexOf(' ');
    if (sp < 0) {
      Serial.println("ERR SPEED_MS requires argument");
      return;
    }
    int motorIdx = 0;
    long v = 0;
    String arg = cmd.substring(sp + 1);
    if (arg.indexOf(' ') >= 0) {
      String first = arg.substring(0, arg.indexOf(' '));
      String second = arg.substring(arg.indexOf(' ') + 1);
      if (!parseMotor(first, motorIdx) || second.length() == 0) {
        Serial.println("ERR SPEED_MS format");
        return;
      }
      v = second.toInt();
    } else {
      v = arg.toInt();
    }
    if (v < 1) v = 1;
    if (v > 50) v = 50;
    if (motorIdx < 0 || motorIdx > 1) {
      motorIdx = 0;
    }
    stepDelayUs[motorIdx] = (unsigned int)(v * 1000L);
    Serial.println("OK");
    return;
  }

  if (cmd.startsWith("SPEED_US")) {
    int sp = cmd.indexOf(' ');
    if (sp < 0) {
      Serial.println("ERR SPEED_US requires argument");
      return;
    }
    long v = cmd.substring(sp + 1).toInt();
    if (v < 50) v = 50;
    if (v > 50000) v = 50000;
    stepDelayUs[0] = (unsigned int)v;
    Serial.println("OK");
    return;
  }

  if (cmd.startsWith("ENABLE")) {
    int sp = cmd.indexOf(' ');
    if (sp < 0) {
      Serial.println("ERR ENABLE requires argument");
      return;
    }
    int v = cmd.substring(sp + 1).toInt();
    setEnabled(v != 0);
    Serial.println("OK");
    return;
  }

  Serial.println("ERR Unknown command");
}

void setup() {
  pinMode(PIN_STEP[0], OUTPUT);
  pinMode(PIN_DIR[0], OUTPUT);
  pinMode(PIN_STEP[1], OUTPUT);
  pinMode(PIN_DIR[1], OUTPUT);
  pinMode(PIN_EN, OUTPUT);

  digitalWrite(PIN_STEP[0], LOW);
  digitalWrite(PIN_DIR[0], LOW);
  digitalWrite(PIN_STEP[1], LOW);
  digitalWrite(PIN_DIR[1], LOW);

  Serial.begin(115200);
  delay(300);

  setEnabled(true);
  Serial.println("READY");
}

void loop() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n') {
      handleCommand(line);
      line = "";
    } else if (c != '\r') {
      line += c;
      if (line.length() > 128) {
        line = "";
      }
    }
  }
}
