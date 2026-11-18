# 28BYJ-48 + ULN2003 顯微鏡移動穩定化

> 2026-09-16 候選版本更新：目前雙板 X/Y continuous 控制鏈已統一固定
> 0.02 RPM。預熱、backlash、固定方向靠近、掃描啟動及換軸／續掃補償
> 已在 GUI、driver 與韌體入口隔離。以下是保留的歷史調校文件，不能
> 直接作為目前操作指引。現行規則見 [FIXED_RPM_MOTION.md](FIXED_RPM_MOTION.md)。

本專案使用 28BYJ-48 + ULN2003 時，主要誤差來源不是程式座標，而是減速齒輪 backlash、靜摩擦、方向切換後齒輪尚未預載，以及拍照前載台尚未完全停止。

## 已整合的控制策略

1. 半步驅動

Arduino 韌體使用 8 相 half-step 序列。這是 28BYJ-48 在 ULN2003 上較適合微小移動的方式。

2. 線圈保持

`arduino_28byj48_uln2003_serial.ino` 預設在移動後保持最後相位，不再每次 `MOVE` 後立刻釋放線圈。這可降低拍照前的回彈與鬆動。

可用指令：

```text
HOLD 1
HOLD 0
STOP
```

3. 啟動預熱

GUI 新增「馬達預熱」按鈕，也會在蛇行拍攝與批次拍攝前自動預熱。預設：

```text
預熱步數 = 6
預熱次數 = 2
```

流程為：

```text
+6 steps
-6 steps
+6 steps
-6 steps
```

這會先讓齒輪吃到同一側並降低靜摩擦影響。

4. 固定方向靠近

GUI 預設啟用「固定方向靠近」。若目標移動方向和指定靠近方向相反，程式會先超過目標，再用固定方向回到目標。

例：目標是 `-8`，固定靠近方向是 `+1`，靠近補償是 `6`：

```text
先走 -14
再走 +6
淨位移 = -8
最後受力方向 = +1
```

這比只加 backlash 步數更適合顯微鏡，因為最終位置會由同一個機械受力方向抵達。

5. 拍照前等待

GUI 既有「settle ms」仍然有效。建議：

```text
400x：250 到 400 ms
1000x：400 到 600 ms
```

6. 影像回饋校正

GUI 新增 `X影像校正` 與 `Y影像校正`。此功能會用相機畫面量測每次移動後實際位移，不再只看馬達步數。

流程：

```text
擷取基準畫面
正向移動 N 次，每次記錄影像位移
反向移動 N 次，每次記錄影像位移
輸出 CSV / JSON 報告
```

輸出位置：

```text
output/motion_feedback_X_時間/
output/motion_feedback_Y_時間/
```

重點欄位：

```text
dominant_shift_px：主軸實際影像位移
orthogonal_shift_px：非主軸漂移
px_per_step：每 half-step 約等於多少 pixel
response：phase correlation 信任分數
change_score：前後畫面變化分數
```

判讀方式：

```text
std_abs_px_per_step 越小，移動越穩
mean_orthogonal_shift_px 越小，軸間串動越少
positive_direction 與 negative_direction 差距越小，正反轉越一致
response 太低代表畫面紋理不足或移動過大
```

## 建議初始參數

```text
X 每次移動步數：依視野 overlap 實測
Y 每次移動步數：依視野 overlap 實測
反轉補償 X/Y：先保留原值或用 backlash 校正
預熱步數：6
預熱次數：2
靠近補償：6
X/Y 靠近方向：1
settle ms：300
影像回饋次數：10
```

如果畫面仍有明顯回彈，優先增加 `settle ms`，再增加 `靠近補償`。不要一開始就大幅增加 backlash，否則小步移動會被補償量主導。

## 實測 SOP

1. 找一個清楚的紅血球或白血球邊界。
2. 按「馬達預熱」。
3. 用 X 前進移動 5 到 10 次，每次拍照或觀察畫面位移。
4. 用 X 後退重複測試。
5. 若反轉第一下幾乎不動，增加「靠近補償」。
6. 若每次停下後畫面仍慢慢漂，增加 `settle ms`。
7. Y 軸同樣測一次。
8. 按 `X影像校正` / `Y影像校正`，查看輸出的 `motion_feedback_summary.json`。

## 注意事項

- ULN2003 不是電流控制型步進驅動器，精度和扭力有限。
- 28BYJ-48 有塑膠減速齒輪，方向切換一定會有 backlash。
- 如果線圈長時間保持導通會發熱；目前 STOP 保持通電，長時間不用時應使用 RELEASE／GUI 釋放馬達或斷線。
- 若未來需要更高精度，建議改用 NEMA 步進馬達 + TMC2209 / DRV8825 + 消 backlash 機構。
