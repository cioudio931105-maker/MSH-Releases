環境與執行說明
=================

簡介
----
此專案包含 `Image.py`，用來讀取 `cell_images` 資料夾內的 JPG 影像並嘗試進行 panorama 拼接（使用 OpenCV 的 Stitcher）。

必要套件
--------
請使用虛擬環境並安裝以下套件：

- `numpy`
- `opencv-contrib-python` （包含 stitching 模組）

快速建立虛擬環境（PowerShell）
--------------------------------
在專案根目錄執行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

快速建立虛擬環境（cmd / batch）
--------------------------------
```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

執行程式
-------
確保 `cell_images` 資料夾有 JPG 檔，然後在虛擬環境中執行：

```powershell
python Image.py
```

輸出
----
成功拼接後會產生 `stitched_output.jpg`。

故障排除
--------
- 若安裝 `opencv-contrib-python` 時遇到問題，請確認 Python 版本與 wheel 相容性（建議使用 Python 3.8+）。
- 若拼接失敗，可嘗試減少 `max_images` 或縮小 `resize_width` 參數。

檔案
----
- `Image.py`: 主程式（拼接程式）。
- `requirements.txt`: 相依套件清單。

若要我為你自動建立 venv 或直接跑一次測試，告訴我你要我替你做哪一步。 
