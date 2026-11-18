# 28BYJ-48 減速馬達式連續控制

28BYJ-48 原本就是內含減速齒輪箱的步進馬達。這份韌體讓它以類似一般減速馬達的方式持續正轉、反轉和調速，同時保留步數定位功能。

## 接線

Arduino Uno/Nano 與 ULN2003：

| Arduino | ULN2003 |
|---|---|
| D8 | IN1 |
| D10 | IN2 |
| D9 | IN3 |
| D11 | IN4 |
| GND | GND |

馬達建議使用獨立穩定的 5V 電源供應 ULN2003，電源 GND 必須與 Arduino GND 共地。不要直接由 Arduino I/O 腳位驅動馬達。

## 上傳

1. 使用 Arduino IDE 開啟 `28byj48_geared_motor.ino`。
2. 選擇正確的 Arduino 開發板與 COM 埠。
3. 上傳後開啟序列監控視窗。
4. 設定 `115200 baud`，行尾選擇 `Newline`。

## 指令

```text
RUN CW 8
RUN CCW 6
SPEED_RPM 10
SPEED_MS 8
STOP
RELEASE
MOVE 4096
MOVE -2048
HOLD 1
STATUS
PING
```

- `RUN CW 8`：以約 8 RPM 持續正轉。
- `RUN CCW 6`：以約 6 RPM 持續反轉。
- `SPEED_MS 8`：相容現有專案的單馬達速度指令。
- `STOP`：停止並保持扭力。
- `RELEASE`：停止並關閉線圈，馬達不再保持位置。
- `MOVE 4096`：名義上一圈；不同齒輪箱會有少量誤差。

建議負載運轉從 6–8 RPM 開始，不宜超過 12 RPM。程式將輸入限制在 0.2–15 RPM，速度過高時 28BYJ-48 容易失步。
