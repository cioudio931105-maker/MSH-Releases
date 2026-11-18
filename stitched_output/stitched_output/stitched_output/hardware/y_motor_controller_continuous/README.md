# Y 軸 28BYJ-48 持續旋轉相容版

這是由原始 `y_motor_controller/y_motor_controller.ino` 延伸的新版本，原檔未被覆蓋。

## 接線

沿用原本 Y 馬達接線：

| ULN2003 | Arduino |
|---|---:|
| IN1 | D4 |
| IN2 | D5 |
| IN3 | D6 |
| IN4 | D7 |

使用獨立穩定的 5V 馬達電源，並將電源 GND 與 Arduino GND 共地。

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
- `SPEED_RPM <rpm>`：設定 0.01–15 RPM；帶負載建議不超過 12 RPM。
- `STOP`／`RELEASE`：立即停止並釋放線圈。

## 修正

- 正確拒絕雙馬達探測，避免單馬達 Arduino 被誤判。
- `CALI` 使用可中止的非阻塞前進／返回流程。
- `WARMUP` 執行期間可接受 `STOP` 或 `RELEASE`。
- 保留 `MOVE`、`SPEED_MS`、`DIR`、`HOLD`、`PAUSE`、`RESUME`、`STATUS` 等原有指令。

## 上傳

使用 Arduino IDE 開啟 `y_motor_controller_continuous.ino`，選擇 Y 馬達所使用的 Arduino 與 COM 埠後上傳。序列速度為 `115200`。
