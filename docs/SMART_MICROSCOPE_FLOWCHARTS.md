# 智慧化顯微鏡病理影像掃描與 AI 輔助分析系統 - 流程圖

用途：期末成果報告、簡報、專題展示  
格式：Mermaid，可直接貼到支援 Mermaid 的 Markdown、Notion、HackMD、GitHub 或簡報工具中使用。

## 1. 系統整體流程圖

```mermaid
flowchart TD
    A["啟動系統"] --> B["選擇操作模式"]

    B --> C["可選離線影像拼接"]
    B --> D["Basler 即時偵測"]
    B --> E["蛇形掃描與白血球擷取"]
    B --> F["資料集準備與模型訓練"]

    C --> C1["讀取顯微鏡影像資料夾"]
    C1 --> C2["影像前處理<br/>平場校正、降噪、CLAHE"]
    C2 --> C3["相鄰影像對位<br/>phase / ECC / ORB / SIFT"]
    C3 --> C4["建立拼接座標與 canvas"]
    C4 --> C5["影像融合<br/>feather / multiband"]
    C5 --> C6["拼接後 AI 偵測"]
    C6 --> C7["輸出 stitched image、JSON、CSV、debug 圖"]

    D --> D1["開啟 Basler 相機"]
    D1 --> D2["載入 YOLO / ONNX / SSD 模型"]
    D2 --> D3["逐 frame 執行 AI 偵測"]
    D3 --> D4["顯示 bounding box、label、confidence"]
    D4 --> D5["保存偵測 crop 或 frame"]
    D5 --> D6["輸出 detections.json 與 session_summary.json"]

    E --> E1["產生全玻片蛇形掃描路徑"]
    E1 --> E2["移動 XY stage 到下一座標"]
    E2 --> E3["1000x preview 偵測 WBC"]
    E3 --> E4{"是否偵測到符合條件的 WBC？"}
    E4 -- "否" --> E9{"是否還有下一座標？"}
    E4 -- "是" --> E5["暫停 XY stage"]
    E5 --> E6["確認焦距與影像清晰度"]
    E6 --> E7["拍攝 1000x WBC 影像"]
    E7 --> E8["裁切 WBC 並寫入 metadata.csv"]
    E8 --> E12["恢復 stage 並繼續掃描"]
    E12 --> E9
    E9 -- "是" --> E2
    E9 -- "否" --> E10{"是否需要拼接全景？"}
    E10 -- "是" --> C
    E10 -- "否" --> E11["輸出 WBC crop、metadata、summary"]

    F --> F1["整理人工標註與外部資料集"]
    F1 --> F2["轉換成 YOLO / VOC 格式"]
    F2 --> F3["訓練 YOLO 或 SSD 模型"]
    F3 --> F4["評估模型與調整 threshold"]
    F4 --> F5["更新模型 preset"]
```

## 2. 影像拼接可選流程圖

```mermaid
flowchart TD
    A["掃描完成或需要全景圖"] --> A1{"是否需要影像拼接？"}
    A1 -- "否" --> A2["跳過拼接<br/>保留 WBC crop、metadata、summary"]
    A1 -- "是" --> B["建立 StitchingConfig"]
    B --> C["建立輸出資料夾與 log"]
    C --> D["偵測 runtime<br/>CPU / CUDA / YOLO device"]
    D --> E["讀取並排序影像"]
    E --> F{"影像數量是否很大？"}

    F -- "是" --> G["啟用 streaming mode<br/>逐張處理降低記憶體用量"]
    F -- "否" --> H["一次載入影像並前處理"]

    G --> I["影像前處理"]
    H --> I

    I --> I1["平場校正<br/>修正照明不均"]
    I1 --> I2["去雜訊"]
    I2 --> I3["CLAHE 局部對比增強"]
    I3 --> I4["產生 alignment_gray 與 blend_bgr"]

    I4 --> J{"是否啟用 YOLO guidance？"}
    J -- "是" --> K["偵測細胞 ROI 並建立 guidance mask"]
    J -- "否" --> L["直接進入影像對位"]
    K --> L

    L --> M["計算相鄰影像位移"]
    M --> M1["優先嘗試 phase correlation"]
    M1 --> M2["必要時改用 ECC / ORB / SIFT"]
    M2 --> M3["過濾不合理位移"]

    M3 --> N["建立 tile placements"]
    N --> O["建立最終 canvas"]
    O --> P{"依資料量與效能模式選擇融合方法"}
    P --> P1["影像少且 canvas 不大<br/>使用 multiband"]
    P --> P2["影像多或 canvas 大<br/>使用 feather"]
    P1 --> Q["輸出拼接影像"]
    P2 --> Q

    Q --> R["可選：拼接後 AI 偵測"]
    R --> S["輸出結果"]
    S --> S1["stitched_result.png"]
    S --> S2["overlay_preview.png"]
    S --> S3["shifts.json / shifts.csv"]
    S --> S4["post_stitch_detection/"]
```

## 3. 白血球蛇形掃描擷取流程圖

```mermaid
flowchart TD
    A["開始全玻片 WBC 蛇形掃描"] --> B["建立輸出資料夾"]
    B --> C["產生垂直蛇形路徑"]
    C --> D["開啟 camera 與 stage"]
    D --> E["移動到目前座標"]
    E --> F["讀取 1000x preview frame"]
    F --> G["AI 偵測白血球"]
    G --> H{"是否偵測到可用 WBC？"}

    H -- "否" --> I{"是否還有下一座標？"}
    I -- "是" --> E
    I -- "否" --> Z["結束掃描並輸出 summary.json"]

    H -- "是" --> J["停止 XY stage"]
    J --> P["確認 1000x 影像清晰度"]
    P --> Q["使用者手動對焦並按 Enter"]
    Q --> R["拍攝 1000x WBC 影像"]
    R --> S["再次執行 WBC 偵測"]
    S --> T["根據 bbox 裁切 WBC"]
    T --> U["保存 original frame"]
    U --> V["保存 cropped cell"]
    V --> W["寫入 metadata.csv"]
    W --> X["恢復 XY stage 並繼續掃描"]
    X --> I
    Z --> AA{"是否需要拼接全景？"}
    AA -- "是" --> AB["另行執行影像拼接流程"]
    AA -- "否" --> AC["只輸出 WBC 影像、metadata、summary"]
```

## 4. 報告用短版流程圖

如果報告版面有限，可以使用此版本：

```mermaid
flowchart LR
    A["全玻片蛇形掃描"] --> B["1000x preview AI 偵測"]
    B --> C{"偵測到 WBC？"}
    C -- "是" --> D["暫停 stage 並拍攝 WBC"]
    D --> E["裁切 WBC 與寫入 metadata"]
    C -- "否" --> F["繼續下一掃描座標"]
    E --> F
    F --> G{"是否需要拼接？"}
    G -- "是" --> H["影像對位與融合拼接"]
    G -- "否" --> I["輸出 WBC crop / JSON / CSV"]
    H --> I
    I --> J["資料集與模型回饋"]
```

## 5. 硬體 X/Y 馬達控制流程圖

```mermaid
flowchart TD
    A["開始硬體馬達控制"] --> B["執行硬體預檢"]
    B --> B1["列出 serial ports"]
    B1 --> B2["檢查 X 軸與 Y 軸控制埠"]
    B2 --> B3["開啟或 ping Arduino 控制器"]
    B3 --> C{"serial port 是否正常？"}

    C -- "否" --> C1["回報錯誤<br/>port 未偵測、被占用或無 PONG"]
    C1 --> Z["停止硬體流程"]

    C -- "是" --> D["建立 SerialXYStage / HardwareStage"]
    D --> E["連接 ArduinoStepper"]
    E --> F["設定馬達速度、timeout、hold"]
    F --> G["接收目標座標 target_x / target_y"]
    G --> H["讀取目前座標 current_x / current_y"]
    H --> I["計算相對位移 dx / dy"]
    I --> J{"dx 或 dy 是否需要移動？"}

    J -- "否" --> J1["維持目前座標"]
    J1 --> R["回報移動完成"]

    J -- "是" --> K["依方向符號修正 X/Y 步數"]
    K --> L{"控制器類型"}
    L -- "單一雙軸控制器" --> M["送出 motor_id=0/1 的移動命令"]
    L -- "X/Y 獨立控制器" --> N["分別送出 X stepper 與 Y stepper 命令"]
    M --> O["等待馬達動作完成"]
    N --> O
    O --> P["更新 current_x / current_y"]
    P --> R["回報移動完成"]

    R --> S{"是否收到停止或結束指令？"}
    S -- "否" --> G
    S -- "是" --> T["送出 stop 命令"]
    T --> U["關閉 serial / stepper 連線"]
    U --> V["結束硬體馬達控制"]
```

## 6. 簡化版全部過程流程圖

適合放在報告前段或簡報摘要頁，讓讀者先快速理解整個系統以全玻片掃描與白血球擷取為主，影像拼接則依需求作為可選分支。

```mermaid
flowchart TD
    A["啟動系統"] --> B["硬體與相機預檢"]
    B --> B1["確認 Basler 相機"]
    B --> B2["確認 X/Y 馬達與 serial port"]
    B1 --> C["設定 1000x 掃描參數"]
    B2 --> C

    C --> D["建立全玻片蛇形掃描路徑"]
    D --> E["控制 X/Y stage 移動"]
    E --> F["1000x preview AI 偵測 WBC"]
    F --> G{"是否偵測到 WBC？"}
    G -- "是" --> H["暫停 stage 並拍攝 1000x WBC"]
    H --> I["裁切白血球並寫入 metadata"]
    I --> J["恢復 stage 並繼續掃描"]
    G -- "否" --> J
    J --> K{"掃描完成後是否需要拼接？"}
    K -- "是" --> L["影像對位與融合拼接"]
    K -- "否" --> M["跳過拼接"]
    L --> N["輸出 stitched image、WBC crop、JSON、CSV"]
    M --> N
    N --> O["回饋資料集並更新模型"]
```
