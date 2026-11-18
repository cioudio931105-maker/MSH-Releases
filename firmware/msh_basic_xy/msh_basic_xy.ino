// SPDX-License-Identifier: AGPL-3.0-only
// GUI adapter for Mike McCauley's AccelStepper ConstantSpeed example (GPLv3).
// Same FULL4WIRE mode, setMaxSpeed(1000), setSpeed(+/-50), runSpeed().
// Adaptations: two motors, agreed pins, serial buttons, stop/normal-close.
// X IN1..4 = D4,D5,D6,D7; Y IN1..4 = D8,D9,D10,D11.
#include <AccelStepper.h>

// Library pin order is IN1, IN3, IN2, IN4; physical wiring stays as above.
AccelStepper motorX(AccelStepper::FULL4WIRE, 4, 6, 5, 7);
AccelStepper motorY(AccelStepper::FULL4WIRE, 8, 10, 9, 11);

void stopHolding() {
  motorX.setSpeed(0);
  motorY.setSpeed(0);
}

void powerOff() {
  stopHolding();
  motorX.disableOutputs();
  motorY.disableOutputs();
}

void setup() {
  motorX.setMaxSpeed(1000);
  motorY.setMaxSpeed(1000);
  // The GUI starts motion only while a direction button is held.
  powerOff();
  Serial.begin(115200);
}

void loop() {
  if (Serial.available()) {
    switch (Serial.read()) {
      case 'a': stopHolding(); motorX.setSpeed(50); break;
      case 'b': stopHolding(); motorX.setSpeed(-50); break;
      case 'c': stopHolding(); motorY.setSpeed(50); break;
      case 'd': stopHolding(); motorY.setSpeed(-50); break;
      case 's': stopHolding(); break;
      case 'q': powerOff(); break;
    }
  }
  motorX.runSpeed();
  motorY.runSpeed();
}
