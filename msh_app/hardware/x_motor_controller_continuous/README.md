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
MOTION_POLICY
FIRMWARE_ID
RUN CW 0.020
RUN CCW 0.020
SPEED_RPM 0.020
STOP
RELEASE
STATUS
```

- `RUN CW [rpm]`：固定 0.02 RPM 持續正轉。
- `RUN CCW [rpm]`：固定 0.02 RPM 持續反轉。
- `SPEED_RPM 0.020`：確認固定速度；其他速度回覆 ERR。SPEED_MS 僅接受 732 作為相容別名，實際半步間隔固定 732422 微秒。
- `STOP`：立即停止，保持當前相位通電以維持位置。
- `RELEASE`：立即停止並關閉全部線圈。

`STOP` 後馬達與 ULN2003 會持續通電發熱。長時間不使用、關閉 GUI 或要移除保持力時，必須送出 `RELEASE`。

## 相容性修正

- 單馬達控制器會拒絕 `SPEED_MS 1 700` 雙馬達探測，避免電腦端誤判。
- `STOP`、`PAUSE`、`RESUME`、`STATUS` 因此維持使用既有單馬達格式；`STOP` 保持通電，`RELEASE` 明確釋放線圈。
- RUN、MOVE、CALI 正返程與 RESUME 共用底層相位輸出限速；連續小步指令不能重設間隔。CALI 是往返測試，仍只使用 0.02 RPM。
- WARMUP 明確拒絕且不移動；AUTOWARM 只接受 0，自動預熱預設关闭。原始預熱程式碼保留作歷史參考。

## 上傳

此候選版本需搭配同版 GUI/driver；新 driver 以唯讀 MOTION_POLICY 檢查
RPM=0.020、STEPS_PER_REV=4096、STEP_US=732422、PRELOAD=OFF。
舊版與其他 legacy/雙軸 sketch 不具此契約，會被拒絕連線。
2026-09-16 已上傳並讀回驗證成功，唯讀身分與規則查询通過；實際移動尚待驗證。
FIRMWARE_ID 回覆 X 軸標記 MSH-B-X-01、版本 MSH_FIXED_002RPM_V1、
BUILD=20260916-01、TOPOLOGY=DUAL_UNO，不改變馬達狀態。

使用 Arduino IDE 開啟 `x_motor_controller_continuous.ino`，選擇原本 X 馬達 Arduino 的開發板與 COM 埠後上傳。序列速度為 `115200`。
