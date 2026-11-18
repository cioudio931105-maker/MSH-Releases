# 0.02 RPM 固定運動契約（2026-09-16 候選）

使用者要求所有運動均以 0.02 RPM 為底層，預熱與補償保持隔離。
此文件取代歷史調校文件的操作預設。2026-09-16 已燒錄 X/COM3 與 Y/COM4，
完成寫入讀回及非運動通訊驗證；B 地安裝版 GUI 尚未更新。

## 支援範圍

目前為兩塊 UNO、各控制一軸的 X/Y continuous sketch，D4–D7 接線不變。
其他保留的 legacy sketch／單板雙軸版本未改為此契約，不得當作本次候選。
Python 共用規則在根目錄 `msh_motion_policy.py`，Arduino 在相位輸出函式
`applyStep` 執行相同限速。新功能必須沿用共用 driver 與這兩份韌體的
移動入口；不能自行另寫速度、直接輸出相位或重新啟用預載功能。

## 速度與路徑

沿用名義 4096 half-steps/output revolution，0.02 RPM 對應
732421.875 微秒／半步，韌體取 732422 微秒（約 1.3653 steps/s）。
這是名義減速輸出軸轉速，並非已量測的平台位移精度。
固定轉速是移動期間的步進時序；拍攝、暫停、停止仍可以沒有步進。

| 入口 | 現行行為 |
|---|---|
| 手動按鈕／方向鍵、RUN CW/CCW | 固定 0.02 RPM |
| MOVE、GUI 座標移動、WBC 掃描、蛇行錄影 | 同一底層間隔，依要求步數移動 |
| CALI 正程及返程 | 固定 0.02 RPM；非阻塞且可停止 |
| 連續 MOVE 1、切換 RUN、PAUSE/RESUME | 不重設最後一步時鐘，不得繞過限速 |
| STOP | 終止運動，保留當前線圈狀態；已釋放時不重新加電 |
| RELEASE、GUI 斷線／關閉 | 終止運動並釋放線圈 |
| SPEED_RPM | 只接受 0.020；其餘回覆 ERR FIXED_RPM |
| SPEED_MS | 只接受 732 相容值；底層仍為固定 732422 微秒 |

Driver MOVE/CALI 等待時間按固定間隔及實際往返步數計算；收到 STOP／
RELEASE 回覆即報告動作中止。GUI 不再在停止或掃描結束時恢復 5/8 ms。
掃描時間會隨固定低速增加，需重新驗證實際拍攝流程及估時。

## 預熱與補償隔離

A 地 `1f8b713` 隱藏了正式 GUI 的預熱、補償及舊掃描控制面板，
但舊函式與韌體自動預熱仍存在。本候選補上執行入口的隔離：

- 韌體開機自動預熱關閉；WARMUP 拒絕且不移動，AUTOWARM 1 拒絕。
- Driver warmup 不會失敗後改送正反 MOVE。
- 回差、固定方向靠近、掃描啟動 72 步、換軸與續掃額外步數均不執行。
- 保留歷史程式、參數及隱藏面板；舊設定值不會自行啟用這些動作。
- CALI 僅保留明確要求的往返測試，不會在普通 MOVE 前自動執行。

## GUI／韌體相容檢查

連線只讀 `MOTION_POLICY`，預期回覆：

```text
MOTION_POLICY RPM=0.020 STEPS_PER_REV=4096 STEP_US=732422 PRELOAD=OFF
```

不符即關閉該連線。移除原本會寫 SPEED_MS 的能力探測。
另可唯讀查詢 `FIRMWARE_ID`，取得 MSH_FIXED_002RPM_V1、AXIS、
BOARD、BUILD=20260916-01、TOPOLOGY=DUAL_UNO。
X 的軟體標籤為 MSH-B-X-01，Y 為 MSH-B-Y-01；這是 Flash 內的人工指派
標籤，並非硬體序號。GUI 目前仍由使用者選擇軸別 COM，
MSH-020 的自動軸別拒絕／完整能力握手仍是獨立工作。
必須配套更新 GUI/driver 和兩塊板子；已安裝的 v0.1.3 尚未包含本次修正。

## 驗證與部署狀態

- X/Y 以 Arduino AVR 1.8.8、arduino:avr:uno 編譯通過，
  加入身分標記後各 12208 bytes Flash / 287 bytes SRAM；編譯期斷言核對 732422 微秒。
- 47 項相關 firmware contract、driver mock、GUI mock、預覽及蛇行錄影
  測試通過；另 WBC 模組 10/11 通過，一項裁切檔案數量測試在未修改的
  603e2be 基底也同樣失敗。此既有影像輸出問題未在本次擴大修改。
- 兩塊原有 Flash 均已讀取 32768 bytes 備份並重新核對成功，
  再依 X/COM3、Y/COM4 寫入各 12208 bytes 並讀回驗證通過。
  FIRMWARE_ID 的軸別／標籤及 MOTION_POLICY 符合預期，兩者均回覆
  PONG 與 STATUS IDLE 0 0 0。未發送 RUN、MOVE、CALI 或預熱命令。
- 燒錄紀錄及雜湊見 [ARDUINO_FLASH_20260916.md](ARDUINO_FLASH_20260916.md)；
  使用者已確定未來整合單板雙軸，目前維持雙板，尚未修改接線或採用單板韌體。
- 實機仍需驗證轉速、方向、快速停止、保持／釋放、溫升與完整 GUI 流程。
  無實體限位及硬體急停；STOP 是軟體命令。長時間保持會持續通電，
  閒置時使用 RELEASE。0.02 RPM 本身不代表可以省略行程安全檢查。
