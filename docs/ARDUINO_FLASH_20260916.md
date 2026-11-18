# B 地 Arduino 燒錄與交接紀錄 — 2026-09-16

使用者已授權將固定 0.02 RPM 韌體燒入相對應板子，加入不影響功能的
識別標記，並把歷史及交接資料保存到 D 槽。未來確定整合單板雙軸，
本次維持兩塊 UNO、各一個 ULN2003/28BYJ-48、D4–D7、115200 baud。

## 已完成

| 實體控制器 | 本次 COM | 舊 boot banner | 燒錄後 FIRMWARE_ID |
|---|---|---|---|
| X | COM3 | READY Y-motor | MSH_FIXED_002RPM_V1 AXIS=X BOARD=MSH-B-X-01 BUILD=20260916-01 TOPOLOGY=DUAL_UNO |
| Y | COM4 | READY X-motor | MSH_FIXED_002RPM_V1 AXIS=Y BOARD=MSH-B-Y-01 BUILD=20260916-01 TOPOLOGY=DUAL_UNO |

COM 是當天連接資訊，日後可能改變。BOARD 是人工指派的韌體標籤，
不是不可複製的硬體序號；查詢只輸出文字，不驅動 LED、腳位或馬達。
本次上傳前的物理映射來自先前反覆 PING 的 LED 觀察及使用者確認。

1. 上傳前兩板均回覆 PONG 和 STATUS IDLE 0 0 0。
2. avrdude 8.0-arduino.1 以 arduino bootloader／ATmega328P／115200 baud
   讀取各 32768 bytes Flash，保存 Intel HEX，另行重新讀取比對均通過。
3. Arduino AVR 1.8.8、arduino:avr:uno 編譯 X/Y 成功：
   各 12208 bytes Flash、287 bytes SRAM。
4. 使用不含 bootloader 的 .ino.hex，依序上傳 COM3/X、COM4/Y；
   avrdude 寫入後均讀回並驗證全部 12208 bytes 成功。
5. 各板上傳後唯讀查詢 FIRMWARE_ID、MOTION_POLICY、PING、STATUS。
   身分符合上表；兩者規則皆為：

```text
MOTION_POLICY RPM=0.020 STEPS_PER_REV=4096 STEP_US=732422 PRELOAD=OFF
PONG
STATUS IDLE 0 0 0
```

上傳後開啟序列埠時未另外捕獲 READY banner，故以明確的 FIRMWARE_ID
查詢驗證軸別，不將未觀察的 banner 當成已驗證。未發送任何移動命令。

## SHA-256（檔案 bytes）

| 檔案 | SHA-256 |
|---|---|
| COM3_X_before_flash.hex | 7127ca271c59a6e9f4c912d42d59df25a8042f7fb8cb854082369319565b210d |
| COM4_Y_before_flash.hex | 641184c4847618dc8075dd4d21fb7f3f866244b28c0152cddd7a53f98bc9de9c |
| X_new_firmware/x_motor_controller_continuous.ino.hex | d5b5fa4d0e73d7cbf121068cebfd97d80731cd195a4338766eaf0c95e3654f80 |
| Y_new_firmware/y_motor_controller_continuous.ino.hex | ef9fb779dcc3cc1206890b6a3bfa099cb6ed659424f79bb43b4778cda16a1728 |

## D 槽交接位置

`02_B地產生_帶回A地_20260911/03_B地環境與版本紀錄/Arduino_flash_backup_20260916/`

包含舊 Flash、備份比對／上傳驗證日誌、新韌體建置產物、實機查詢 JSON、
原始碼快照、相對 603e2be 的差異、檔案雜湊及交接 README。
Flash 備份由 bootloader 可讀介面取得，並非 EEPROM／fuses／lock bits 備份；
本次未修改 bootloader、fuses 或 EEPROM，亦未驗證實際回復操作。
需回復時先核對板子物理軸別及此表，不可自動批次還原。

## 收尾及待續

- 本次軟體與韌體改動位於 codex/msh-015-stop-hold，
  基底 603e2be8a695afc89695cc3bd99d5aaa42df677c；截至本紀錄尚未 commit/push，
  分支未設定 upstream。備份檔與建置產物保存在 D，不加入原始碼 Git。
- B 地安裝版 GUI 尚未更新；後續須配套部署本次 driver/GUI。
  47 項相關軟體測試通過；既有 WBC 裁切測試失敗在原基底同樣重現。
- 實際轉速、方向、停止反應、保持／釋放、溫升及完整 GUI 掃描尚未驗收。
  有限位／硬體急停前不得把軟體 STOP 當作硬體急停。
- MSH-021 單板雙軸是確定的後續方向；先保留目前雙板基準，
  後續再設計接線、軸別通訊、共用連線與相容性驗證，不在本次改造。
