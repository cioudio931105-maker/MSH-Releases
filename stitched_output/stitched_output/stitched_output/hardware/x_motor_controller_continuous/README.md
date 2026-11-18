# X 軸 28BYJ-48 持續旋轉相容版

這是由原始 `x_motor_controller/x_motor_controller.ino` 複製後擴充的版本，原檔未被覆蓋。

## 硬體接線

沿用原本接線：

| ULN2003 | Arduino |
|---|---:|
| IN1 | D4 |
| IN2 | D5 |
| IN3 | D6 |
| IN4 | D7 |

使用外接穩定 5V 馬達電源，並將外接電源 GND 與 Arduino GND 共地。

## 新增指令

```text
RUN CW 8
RUN CCW 6
SPEED_RPM 10
STOP
RELEASE
STATUS
```

- `RUN CW [rpm]`：持續正轉。
- `RUN CCW [rpm]`：持續反轉。
- `SPEED_RPM <rpm>`：設定 0.01–15 RPM；28BYJ-48 帶負載建議不超過 12 RPM。
- `STOP`／`RELEASE`：立即停止並釋放線圈。

## 相容性修正

- 單馬達控制器會拒絕 `SPEED_MS 1 700` 雙馬達探測，避免電腦端誤判。
- `STOP`、`PAUSE`、`RESUME`、`STATUS` 因此維持使用既有單馬達格式。
- `CALI` 改用非阻塞狀態流程；校正前進或返回途中均能處理 `STOP`。
- 原有 `MOVE`、`SPEED_MS`、`DIR`、`WARMUP`、`AUTOWARM`、`HOLD` 等指令保留。

## 上傳

使用 Arduino IDE 開啟 `x_motor_controller_continuous.ino`，選擇原本 X 馬達 Arduino 的開發板與 COM 埠後上傳。序列速度為 `115200`。
