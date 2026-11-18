# v0.1.4 第三方來源取得證據

2026-10-20 本機續作紀錄。這是來源與授權補件，**不表示完整對應來源、原生授權相容性或正式發佈驗收已完成**。
目前沒有 commit、push、公開上傳或廠商聯絡，也沒有更動模型／研究資料或硬體設定。

## 已實際取得與驗證的 PyPI 來源

以下 8 份為建置環境已安裝的精確版本；從 PyPI 指定版本 JSON 取得 sdist URL、大小與 SHA-256，
下載後逐一驗證。不執行 setup、建置腳本或安裝動作。最初沙箱 DNS 失敗的紀錄保留，
之後以獲准的唯讀官方下載完成，不能把首次失敗算成成功。

| 套件 | 版本 | 官方來源封存檔 | bytes | SHA-256 | 相同 Python 檔／已檢查檔 |
| --- | --- | --- | ---: | --- | ---: |
| ultralytics | 8.4.123 | [ultralytics-8.4.123.tar.gz](https://files.pythonhosted.org/packages/4d/28/a862b756f25d417efd60b3f78b8e6911832bfcc7bba97e8e6616ece01365/ultralytics-8.4.123.tar.gz) | 1207510 | `f78055bf72fb5804bf5b43a0aee0f22e173f133411441807a9eb4fbb3bec7358` | 240/240 |
| ultralytics-platform | 0.1.5 | [ultralytics_platform-0.1.5.tar.gz](https://files.pythonhosted.org/packages/78/53/898352d8c872aee2aacffb96b2d054d49ef06095c23c85c0f35db1fcd652/ultralytics_platform-0.1.5.tar.gz) | 52592 | `72f6aba7f6251747c7f69d68253036d106e0142242fbc7244b4fa761e265c1ea` | 20/20 |
| ultralytics-thop | 2.1.6 | [ultralytics_thop-2.1.6.tar.gz](https://files.pythonhosted.org/packages/45/20/d6b6aaa8ecf7dbdeaf0c05f73bdcd04cf8ce468d936bc48dbcd368e75baf/ultralytics_thop-2.1.6.tar.gz) | 36364 | `0ec2df8ebd3db35795e1f80cdc8bce6734446dbe989bca1b0c89396353f0f08c` | 7/7 |
| certifi | 2026.7.22 | [certifi-2026.7.22.tar.gz](https://files.pythonhosted.org/packages/a3/c2/24167ea9858356b47a87a50d39908bfdb72ceeefe0041586e704e5376b3a/certifi-2026.7.22.tar.gz) | 138112 | `741e2c3b351ddf169a738da9f2c048608ff7f2c5cc02f1ebc6b118bb090d5d55` | 5/5 |
| tqdm | 4.70.0 | [tqdm-4.70.0.tar.gz](https://files.pythonhosted.org/packages/21/3b/6c24bec5be5e743ffd99576daa5cc077722fc7d5bbc00bd133fa0c698dc6/tqdm-4.70.0.tar.gz) | 795438 | `55b0b0dbd97462d06ebee91e4dac24ed4d4702be82b24f07e6c1d27e08cea220` | 31/31 |
| pyserial | 3.5 | [pyserial-3.5.tar.gz](https://files.pythonhosted.org/packages/1e/7d/ae3f0a63f41e4d2f6cb66a5b57197850f919f59e558159a4dd3a818f5082/pyserial-3.5.tar.gz) | 159125 | `3c77e014170dfffbd816e6ffc205e9842efb10be9f58ec16d3e8675b4925cddb` | 28/28 |
| nvidia-ml-py | 13.610.43 | [nvidia_ml_py-13.610.43.tar.gz](https://files.pythonhosted.org/packages/f0/b5/a8fbc356f768fa5c9cfd646668fd7d34bf55bdd1c6e20754642a64d930d4/nvidia_ml_py-13.610.43.tar.gz) | 52109 | `65437eb73d68d0c62c931ca4d45038472faff03bd0b8729abba4b899f70d60f2` | 2/2 |
| pyinstaller | 6.22.2 | [pyinstaller-6.22.2.tar.gz](https://files.pythonhosted.org/packages/cc/2b/836d9def811c02522e0921d8b8cdf0c16b0545a216e97e71041758057859/pyinstaller-6.22.2.tar.gz) | 4092631 | `89b65a3ad07d9dd5832253e37bc45f31872d10d7f9d5c9fd0fdd6088a83829dd` | 558/558 |

891 個已安裝 Python 來源檔全部與 sdist 內容逐位元相同；這是環境檔案比對，
不是 frozen module membership 的完整推導，也不保證重新建置會產生逐位元相同的 EXE。
PyInstaller 的來源有收集，不表示所有建置工具都屬應用程式執行時依賴。

本機位置：`tmp/lic014-upstream-sources-network/`；下載紀錄 `SOURCE_DOWNLOADS.json`；
逐檔比對 `tmp/lic014-upstream-source-verification.json`。原始封存檔可能含廠商 demo 素材，
全部留在 Git 忽略的查核區，尚未加入應用程式 ZIP／installer／Git，也不可未審查直接公開。
正式交付時還需決定來源附件內容、持續可下載位置與適用授權義務。

## pypylon wrapper 與原生 SDK 的區別

PyPI 26.7 沒有可用的唯一 sdist，本次另外解析官方 GitHub tag，取得固定 commit 的來源快照：

- Tag：`26.7`；commit：`faa641fa8ea163fcc3fd82a0578e382cc64e2ccb`。
- [官方 commit 快照](https://codeload.github.com/basler/pypylon/tar.gz/faa641fa8ea163fcc3fd82a0578e382cc64e2ccb)：23303500 bytes。
- 本機 SHA-256：`d35bff54d89b7325184d42944f96c8858990e117d04da4778f18873b6d0a2b67`。

這個 SHA-256 是官方 HTTPS 下載後本機計算值，未宣稱有獨立上游簽章／checksum。
它提供 wrapper 的建置來源；並未提供 proprietary pylon 原生 DLL 的原始碼或 AGPL 組合許可。
26.7.2 原生 SDK 的適用條款、第三方 notices／來源與組合權利仍未結案。

## 已定位的 OpenCV FFmpeg 原生來源線索

OpenCV 5.0.0 的[官方下載設定](https://github.com/opencv/opencv/blob/5.0.0/3rdparty/ffmpeg/ffmpeg.cmake)
指定 `opencv_3rdparty` commit `06dc20cad65dc7fcf784f70c95d46750520889a7`。
已實際下載該 commit 的 DLL，與候選版內改帶版本後綴的 `opencv_videoio_ffmpeg500_64.dll` 比對：

- SHA-256 完全相同：`7aabff029d1fa47cf56ede4dbbe05dc62da3208f07cd16471d4c966a33f9aa31`。
- 官方設定的 MD5 `a821a1135251859655090c795af05789` 也相符；完整性結論使用 SHA-256。
- 13 份查核檔案全部下載完成（包含 DLL、版本表、readme、license 與建置／來源腳本），沒有執行。
- 同 commit 的[來源腳本](https://github.com/opencv/opencv_3rdparty/blob/06dc20cad65dc7fcf784f70c95d46750520889a7/ffmpeg/download_src.sh)
  指定 FFmpeg `n7.1`、OpenH264 `v2.5.0`、libvpx `v1.16.0`、aom `v3.14.1`。
- 版本表 `libavcodec 61.19.100`、`libavformat 61.7.100` 與本機 DLL 內字串相符。

本機證據：`tmp/lic014-native-source-evidence/NATIVE_SOURCE_EVIDENCE.json`。
已定位的 binary／recipe 並不等於已保存所有巢狀來源、工具鏈／Docker 環境、wrapper source、
patches、重新連結說明，也未實際重建 DLL。[FFmpeg 官方交付指引](https://ffmpeg.org/legal.html)
特別要求來源對應實際散布的 library；上述剩餘項目仍須處理。

## 新補齊的授權文字

- pyserial：從 SHA-256 已驗證的 3.5 sdist 保留 `LICENSE.txt`。
- NVIDIA NVML Python 綁定：保留已安裝 `pynvml.py` 最初完整授權標頭，字節與行註解均不改寫。
- runtime：從原建置套件快取／prefix 保留 12 份 Python、Tcl、Tk、OpenSSL、libffi、bzip2、
  expat、xz、SQLite、zlib、UCRT、VC runtime 文件。Microsoft 提供的 TXT 版本保留，重複 RTF 不複製。

詳細原路徑與 SHA-256 見 [補充 notice](../licenses/SUPPLEMENTAL_NOTICES.md) 與
[runtime 清單](../licenses/runtime/README.md)。既有 114 份文字保留，總計 128 份；catalog 文件另計。
收集器 `scripts/collect_runtime_licenses.py` 僅收指定套件的授權文字，拒絕覆蓋，
不複製原始 conda metadata、二進位或個人路徑。

```powershell
python scripts/collect_runtime_licenses.py --prefix .venv312 --output tmp/runtime-notices-new `
  --package python --package tk --package openssl --package libffi --package bzip2 `
  --package libexpat --package xz --package sqlite --package libzlib `
  --package ucrt --package vc14_runtime
```

12 項相關測試通過，包含新增 runtime notice 的原文保留、只收文字／不收模型、
不匯出絕對路徑、缺套件即拒絕與拒絕覆蓋。

## 尚未滿足的發佈條件

1. pylon 26.7.2 原生 EULA／第三方義務與 Ultralytics／MSH AGPL 組合的權利依據。
2. 其他適用第三方的完整對應來源、patches／建置與重新連結說明，以及穩定下載安排。
3. 三個 Windows API DLL：目前系統 `System32/downlevel` 有同名檔，但 SHA-256 與候選版不同，
   不能因此宣稱已找到原建置檔。原套件來源或當時建置環境證據仍待核對。
4. 最終來源凍結與重新建置、乾淨 Windows、B 地硬體驗收及明確授權後的 commit／push／公開發佈。

先前來源＋installer review ZIP 保持 SHA-256
`270d319932a4bca0ef67c0747096f89a0d4baef4f093a0386d3bd3c20477f402`，
不含本輪補件。這一輪不為尚未釐清的組合重建另一份候選版，避免誤認已放行。
