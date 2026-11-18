/*
  28BYJ-48 + ULN2003 continuous geared-motor controller

  Wiring (Arduino Uno/Nano -> ULN2003):
    D8  -> IN1
    D10 -> IN2
    D9  -> IN3
    D11 -> IN4
    5V external supply -> ULN2003 VCC
    Supply GND <-> Arduino GND

  Serial: 115200 baud, newline-terminated commands
    RUN CW [rpm]       continuous clockwise rotation
    RUN CCW [rpm]      continuous counter-clockwise rotation
    MOVE <steps>       relative half-step move; negative reverses direction
    SPEED_RPM <rpm>    set speed for subsequent RUN/MOVE commands
    SPEED_MS <ms>      legacy project-compatible half-step delay
    SPEED_US <us>      legacy project-compatible half-step delay
    STOP               stop and hold the current position
    RELEASE            stop and de-energize all coils
    HOLD 0|1           choose whether STOP keeps the coils energized
    STATUS             print current state
    PING               reply PONG

  Notes:
    - 4096 half-steps/output revolution is a practical nominal value.
      Individual 28BYJ-48 gearboxes vary slightly; calibrate if angle matters.
    - Keep the default speed at or below 12 RPM under load.
*/

#include <Arduino.h>

constexpr uint8_t MOTOR_PINS[4] = {8, 10, 9, 11};
constexpr uint8_t HALF_STEP_SEQUENCE[8][4] = {
  {1, 0, 0, 0},
  {1, 1, 0, 0},
  {0, 1, 0, 0},
  {0, 1, 1, 0},
  {0, 0, 1, 0},
  {0, 0, 1, 1},
  {0, 0, 0, 1},
  {1, 0, 0, 1},
};

constexpr long HALF_STEPS_PER_OUTPUT_REV = 4096L;
constexpr float DEFAULT_RPM = 8.0F;
// The manual microscope GUI uses a verified 0.02 RPM crawl speed. Keep the
// independent continuous-test command configurable, but permit that speed.
constexpr float MIN_RPM = 0.01F;
constexpr float MAX_RPM = 15.0F;
constexpr size_t COMMAND_BUFFER_SIZE = 64;

enum class MotionMode : uint8_t {
  Stopped,
  Continuous,
  RelativeMove,
};

MotionMode motionMode = MotionMode::Stopped;
bool holdWhenStopped = true;
int8_t directionSign = 1;
long remainingSteps = 0;
long positionSteps = 0;
uint8_t sequenceIndex = 0;
float targetRpm = DEFAULT_RPM;
unsigned long stepIntervalUs = 0;
unsigned long previousStepUs = 0;
char commandBuffer[COMMAND_BUFFER_SIZE];
size_t commandLength = 0;

float clampRpm(float rpm) {
  if (rpm < MIN_RPM) return MIN_RPM;
  if (rpm > MAX_RPM) return MAX_RPM;
  return rpm;
}

void updateStepInterval() {
  targetRpm = clampRpm(targetRpm);
  const float stepsPerSecond =
      (targetRpm * static_cast<float>(HALF_STEPS_PER_OUTPUT_REV)) / 60.0F;
  stepIntervalUs = static_cast<unsigned long>(1000000.0F / stepsPerSecond);
  if (stepIntervalUs < 900UL) stepIntervalUs = 900UL;
}

void writeSequence(uint8_t index) {
  for (uint8_t pin = 0; pin < 4; ++pin) {
    digitalWrite(MOTOR_PINS[pin], HALF_STEP_SEQUENCE[index][pin] ? HIGH : LOW);
  }
}

void releaseMotor() {
  for (uint8_t pin = 0; pin < 4; ++pin) {
    digitalWrite(MOTOR_PINS[pin], LOW);
  }
}

void stopMotor(bool releaseCoils) {
  motionMode = MotionMode::Stopped;
  remainingSteps = 0;
  if (releaseCoils || !holdWhenStopped) {
    releaseMotor();
  } else {
    writeSequence(sequenceIndex);
  }
}

void performOneHalfStep() {
  if (directionSign > 0) {
    sequenceIndex = static_cast<uint8_t>((sequenceIndex + 1U) & 0x07U);
    ++positionSteps;
  } else {
    sequenceIndex = static_cast<uint8_t>((sequenceIndex + 7U) & 0x07U);
    --positionSteps;
  }
  writeSequence(sequenceIndex);

  if (motionMode == MotionMode::RelativeMove) {
    --remainingSteps;
    if (remainingSteps <= 0) {
      stopMotor(false);
      Serial.println(F("DONE"));
    }
  }
}

void serviceMotor() {
  if (motionMode == MotionMode::Stopped) return;

  const unsigned long now = micros();
  if (static_cast<unsigned long>(now - previousStepUs) < stepIntervalUs) return;
  previousStepUs = now;
  performOneHalfStep();
}

void uppercase(char *text) {
  while (*text != '\0') {
    if (*text >= 'a' && *text <= 'z') *text = static_cast<char>(*text - 32);
    ++text;
  }
}

void printStatus() {
  Serial.print(F("STATUS "));
  if (motionMode == MotionMode::Continuous) {
    Serial.print(F("RUNNING"));
  } else if (motionMode == MotionMode::RelativeMove) {
    Serial.print(F("MOVING"));
  } else {
    Serial.print(F("STOPPED"));
  }
  Serial.print(F(" DIR="));
  Serial.print(directionSign > 0 ? F("CW") : F("CCW"));
  Serial.print(F(" RPM="));
  Serial.print(targetRpm, 2);
  Serial.print(F(" POSITION="));
  Serial.print(positionSteps);
  Serial.print(F(" REMAINING="));
  Serial.println(remainingSteps);
}

void handleCommand(char *line) {
  char *command = strtok(line, " \t");
  if (command == nullptr) return;
  uppercase(command);

  if (strcmp(command, "PING") == 0) {
    Serial.println(F("PONG"));
    return;
  }

  if (strcmp(command, "STOP") == 0) {
    stopMotor(false);
    Serial.println(F("OK"));
    return;
  }

  if (strcmp(command, "RELEASE") == 0) {
    stopMotor(true);
    Serial.println(F("OK"));
    return;
  }

  if (strcmp(command, "STATUS") == 0) {
    printStatus();
    return;
  }

  if (strcmp(command, "HOLD") == 0) {
    const char *value = strtok(nullptr, " \t");
    if (value == nullptr) {
      Serial.println(F("ERR HOLD requires 0 or 1"));
      return;
    }
    holdWhenStopped = atoi(value) != 0;
    if (!holdWhenStopped && motionMode == MotionMode::Stopped) releaseMotor();
    Serial.println(F("OK"));
    return;
  }

  if (strcmp(command, "ENABLE") == 0) {
    const char *value = strtok(nullptr, " \t");
    if (value == nullptr) {
      Serial.println(F("ERR ENABLE requires 0 or 1"));
      return;
    }
    if (atoi(value) == 0) {
      stopMotor(true);
    } else if (motionMode == MotionMode::Stopped && holdWhenStopped) {
      writeSequence(sequenceIndex);
    }
    Serial.println(F("OK"));
    return;
  }

  if (strcmp(command, "SPEED_MS") == 0 || strcmp(command, "SPEED_US") == 0) {
    const bool milliseconds = strcmp(command, "SPEED_MS") == 0;
    const char *value = strtok(nullptr, " \t");
    const char *extra = strtok(nullptr, " \t");
    if (value == nullptr || extra != nullptr) {
      Serial.println(F("ERR legacy speed requires one value"));
      return;
    }
    unsigned long interval = strtoul(value, nullptr, 10);
    if (milliseconds) interval *= 1000UL;
    if (interval < 900UL) interval = 900UL;
    stepIntervalUs = interval;
    targetRpm =
        60000000.0F / (static_cast<float>(HALF_STEPS_PER_OUTPUT_REV) * stepIntervalUs);
    Serial.println(F("OK"));
    return;
  }

  if (strcmp(command, "SPEED_RPM") == 0) {
    const char *value = strtok(nullptr, " \t");
    if (value == nullptr) {
      Serial.println(F("ERR SPEED_RPM requires a value"));
      return;
    }
    targetRpm = clampRpm(atof(value));
    updateStepInterval();
    Serial.println(F("OK"));
    return;
  }

  if (strcmp(command, "RUN") == 0) {
    char *direction = strtok(nullptr, " \t");
    char *rpmText = strtok(nullptr, " \t");
    if (direction == nullptr) {
      Serial.println(F("ERR RUN requires CW or CCW"));
      return;
    }
    uppercase(direction);
    if (strcmp(direction, "CW") == 0 || strcmp(direction, "+") == 0) {
      directionSign = 1;
    } else if (strcmp(direction, "CCW") == 0 || strcmp(direction, "-") == 0) {
      directionSign = -1;
    } else {
      Serial.println(F("ERR direction must be CW or CCW"));
      return;
    }
    if (rpmText != nullptr) targetRpm = clampRpm(atof(rpmText));
    updateStepInterval();
    remainingSteps = 0;
    previousStepUs = micros();
    motionMode = MotionMode::Continuous;
    Serial.println(F("OK"));
    return;
  }

  if (strcmp(command, "MOVE") == 0) {
    const char *stepsText = strtok(nullptr, " \t");
    if (stepsText == nullptr) {
      Serial.println(F("ERR MOVE requires steps"));
      return;
    }
    const long requestedSteps = atol(stepsText);
    if (requestedSteps == 0) {
      stopMotor(false);
      Serial.println(F("DONE"));
      return;
    }
    directionSign = requestedSteps > 0 ? 1 : -1;
    remainingSteps = labs(requestedSteps);
    previousStepUs = micros();
    motionMode = MotionMode::RelativeMove;
    Serial.println(F("OK"));
    return;
  }

  Serial.println(F("ERR unknown command"));
}

void serviceSerial() {
  while (Serial.available() > 0) {
    const char incoming = static_cast<char>(Serial.read());
    if (incoming == '\r') continue;
    if (incoming == '\n') {
      commandBuffer[commandLength] = '\0';
      handleCommand(commandBuffer);
      commandLength = 0;
      continue;
    }
    if (commandLength < COMMAND_BUFFER_SIZE - 1) {
      commandBuffer[commandLength++] = incoming;
    } else {
      commandLength = 0;
      Serial.println(F("ERR command too long"));
    }
  }
}

void setup() {
  for (uint8_t pin = 0; pin < 4; ++pin) {
    pinMode(MOTOR_PINS[pin], OUTPUT);
  }
  releaseMotor();
  updateStepInterval();
  Serial.begin(115200);
  Serial.println(F("READY 28BYJ48_GEARED_MOTOR"));
}

void loop() {
  serviceSerial();
  serviceMotor();
}
