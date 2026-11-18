"""Conservative, evidence-labelled deletion explanations; never inspect checkpoints."""
from copy import deepcopy
from pathlib import PurePosixPath


INSTALLED = '若使用另外安裝的 MSH.exe，通常不讀此工作目錄的同名檔案；此判斷不適用於刪除安裝目錄內的檔案。尚未逐項實做刪除測試。'
SOURCE_OTHER = '已核對的日常來源捷徑為 .venv312/pythonw.exe → launch_msh.pyw；此項不是該捷徑的直接入口。其他手動啟動方式與個人路徑仍須確認。'


def item(title, purpose, loss, *, source=SOURCE_OTHER, installed=INSTALLED,
         features='開發、交接或歷史查核；不等同目前日常 GUI 的必要檔案。',
         action='先保留用途與備份；確認不再使用後才列刪除候選。', evidence=(),
         risk='review', certainty='依程式引用或目錄內既有文件／檔案結構判讀；不代表已做刪除實驗。'):
    return dict(title=title, purpose=purpose, source_gui=source, installed_gui=installed,
                features=features, deletion_effect=loss, action=action,
                evidence=list(evidence), risk=risk, certainty=certainty)


def core(title, purpose, features, evidence):
    return item(title,purpose,'刪除整項可能造成來源版匯入或啟動失敗，或使所列功能無法使用。',
                source='來源版直接載入此程式或其模組；不應刪除。',features=features,
                action='保留於正式應用程式來源。',evidence=evidence,risk='required')


def evidence(title,purpose,proof=(),loss=None):
    return item(title,purpose,loss or '不會直接改變目前來源版介面，但會失去這一次測試、交付或失敗原因的證據；歷史結果未必能完全重建。',
                evidence=proof,features='歷史重現、回歸測試、來源或交付追溯。',risk='review')


GROUPS = {
    '.venv312':item('日常來源版的 Python 主環境','內含 Python、影像運算、GUI、AI 與相機通訊等套件；不只是可以隨意清掉的快取。',
        '刪除整個環境，桌面來源捷徑的 pythonw.exe 會消失，來源版 GUI 無法開啟；.venv312-cpu 與示範環境的 pyvenv.cfg 也指向此基底，不能假設它們完全獨立。',
        source='2026-11-09 本機桌面 MSH.lnk 已核對指向此環境的 pythonw.exe；後續若更改捷徑須重新核對。',features='日常 GUI 啟動、影像處理、模型載入；另是兩個 venv 的 Python 基底。',
        action='目前必須保留；若要替換，先建立新環境、改好捷徑並完整驗證。',
        evidence=['install_gui_shortcut.ps1：pythonwCandidates','本機 MSH.lnk 唯讀檢查',' .venv312-cpu/pyvenv.cfg、.venv312-gpu-demo/pyvenv.cfg'],risk='required'),
    '.venv312-cpu':item('CPU 建置與軟體驗證環境','獨立套件集合，用來建置不依賴 CUDA 的 EXE、執行測試及本機 CPU 推論；其 Python 基底仍在 .venv312。',
        '不會移除目前桌面來源 GUI，但會失去本次已驗證的 CPU 打包、測試環境；某些 commands 工具把它當候補 Python，會少一條可用路徑。',
        features='CPU 候選包重建、軟體測試、CPU 訓練／推論。',action='Release 流程仍在進行，建議保留；正式交付與可重建環境確認後再審閱。',
        evidence=['scripts/build_release.ps1：-PythonPath','scripts/commands/*.bat：CPU Python 候補','.venv312-cpu/pyvenv.cfg'],risk='required'),
    '.venv312-gpu-demo':item('GPU 教學示範用的另一份 Python 套件環境','曾為訓練示範準備的 venv；名稱有 GPU 不代表 CUDA 已安裝完整或目前可訓練。',
        '目前來源捷徑不指向這裡；刪除會失去這份示範環境，錄影或訓練腳本若指定此路徑便需重建。',
        features='訓練教學環境；本次未執行其 GPU 可用性驗證。',evidence=['.venv312-gpu-demo/pyvenv.cfg','tmp/msh_training_recording_demo_20261021/gpu_environment_check.json']),
    'launch_msh.pyw':core('日常 GUI 主啟動器','開啟 MSH 視窗、啟動畫面、日誌、單一執行個體與更新選單，也分派封裝後的離線拼接工作。','整個 GUI 啟動、說明／更新、離線工作入口。',['install_gui_shortcut.ps1','launch_msh.pyw：main / dispatch_worker']),
    'msh_app':core('GUI、辨識支援與硬體控制的正式程式','hardware/ 放視窗與 driver，cell_identification/ 放辨識／分類；另保留腳本和 Arduino 原始碼。它是程式，不是拼接輸出。','介面、相機預覽、平台控制、辨識支援；韌體來源的刪除影響須逐檔區分。',['launch_msh.pyw：GUI_SCRIPT','MSH.spec：msh_app/hardware、cell_identification']),
    'cell_stitching_project':core('影像處理與掃描的主要 Python 套件','提供影像對齊、拼接、白血球偵測、掃描錄影、資料整理、訓練與文字繪製等共用功能。','GUI 共用模組及 CLI 拼接、偵測、訓練流程。',['msh_app/hardware/stepper_drag_gui.py：imports','MSH.spec：datas']),
    'microscope_stitcher_project':core('GUI 使用的離線正式拼接引擎','依影像與座標對齊、合成拼接圖，產生品質報告及與基準位置的比較；不只是獨立試驗副本。','GUI 拍攝後拼接、practical-stitch、golden-compare。',['msh_workers.py：WORKER_SCRIPTS','msh_app/hardware/stepper_drag_gui.py：_run_formal_stitcher_session']),
    'msh_runtime.py':core('執行環境、可寫入位置與日誌','區分來源版與 EXE 的資源路徑，建立使用者輸出／日誌目錄並限制同時啟動多個 GUI。','啟動、資源位置、記錄錯誤、輸出路徑。',['launch_msh.pyw：msh_runtime imports']),
    'msh_model_policy.py':core('模型必須由使用者提供的檢查','確認選定模型是存在的本機檔案，避免把缺檔名稱誤作自動下載模型；也提供訓練的本機政策。','模型載入與訓練前檢查。',['cell_stitching_project/cell_identification.py','msh_app/cell_identification/object_detection.py']),
    'msh_motion_policy.py':core('固定馬達操作政策的共用定義','讓 GUI、driver 與掃描工具使用一致的固定速度／步距政策及回覆檢查。','GUI 與 driver 匯入、馬達操作政策檢查；刪檔不是修改馬達參數的方法。',['msh_app/hardware/arduino_stepper.py','tests/test_continuous_firmware_contract.py']),
    'msh_update.py':core('版本更新資訊讀取與驗證','讀取更新描述、比較版本及核對下載資訊，供「說明／檢查更新」選單使用。','更新選單；啟動器也直接匯入此模組。',['launch_msh.pyw：msh_update imports']),
    'msh_version.py':core('應用程式版本來源','統一提供 GUI、版本比較、建置腳本與安裝包所用版本號。','啟動、版本顯示、打包。',['launch_msh.pyw：__version__','scripts/build_release.ps1']),
    'msh_workers.py':core('封裝 EXE 的離線工作分派','只允許啟動指定的拼接／基準比較腳本，讓 EXE 不必假裝成 Python 解譯器。','啟動器匯入、GUI 拼接與基準比較。',['launch_msh.pyw：dispatch_worker','MSH.spec']),
    'msh_distribution.py':item('純應用程式打包的檔案白名單','決定哪些來源、品牌圖和授權檔可進交接包／安裝包，排除研究資料與模型。',
        '目前已開啟的 GUI 不會因此變小；刪除會讓來源稽核、打包或來源交接流程失敗，並失去資料排除規則。',
        features='Release 建置、資料散布邊界、來源交接。',action='保留。',evidence=['MSH.spec：application_files','scripts/audit_application_files.py'],risk='required'),
    'msh_release_model.py':item('舊 v0.1.1 模型身分記錄','保存當時 WBC 單類模型的檔名、SHA-256 與類別；不是模型權重，也不表示現版自動內建該模型。',
        '已核對的目前啟動器未直接使用它；刪除會破壞 tests/test_release_model.py 的歷史身分核對。',features='舊模型來源追溯與回歸測試。',evidence=['msh_release_model.py','tests/test_release_model.py']),
    'sitecustomize.py':item('來源版中文影像標籤的啟動補丁','當專案在 Python 搜尋路徑時自動安裝 OpenCV 的中文文字繪製支援。',
        'GUI 不一定因此無法開，但部分直接執行的腳本可能回到不支援中文的文字繪製方式，輸出圖中文字可能缺字。',
        features='影像上的中文字；與視窗排版不同。',action='保留；若移除需另測所有直接腳本的中文輸出。',evidence=['sitecustomize.py：install_cv2_unicode_puttext_patch'],risk='required'),
    'launch_hardware_gui.ps1':item('來源版啟動檢查與故障診斷入口','選擇可用 Python、檢查 GUI 路徑、顯示啟動錯誤並支援 -CheckOnly／-Diagnostics。',
        '目前桌面捷徑直接走 pythonw → .pyw，並非經這個檔案；刪除仍會讓診斷 bat 與對應啟動檢查失效。',
        features='無法開啟 GUI 時的故障排除。',action='保留。',evidence=['scripts/diagnostics/run_hardware_gui.bat','install_gui_shortcut.ps1'],risk='required'),
    'install_gui_shortcut.ps1':item('建立／更新無 CMD 的來源版捷徑','把桌面或開始功能表捷徑指向 pythonw 與主啟動器，並設定 MSH 圖示。',
        '已建立的捷徑通常仍能使用；刪除會失去重建／修復來源捷徑與 -CheckOnly 檢查能力。',features='安裝與修復來源版入口。',action='保留。',evidence=['install_gui_shortcut.ps1：TargetPath、Arguments'],risk='required'),
    'MSH.spec':item('產生 GUI EXE 的 PyInstaller 配方','指定要封裝的模組、品牌圖、授權、資源與 console=False；不是執行時使用者設定。',
        '來源版 GUI 與既有 EXE 通常仍能開；刪除後無法按目前流程重建相同候選包。',features='Windows EXE 建置及無 CMD 設定。',action='保留於正式來源。',evidence=['scripts/build_release.ps1：PyInstaller MSH.spec'],risk='required'),
    'assets':item('介面圖示與啟動畫面的圖片','包含 MSH 圖示、開啟時的品牌圖片及其版本；這些不是研究影像。',
        '會失去圖示／啟動畫面，捷徑安裝也會因找不到指定圖示而失敗。部分畫面有缺圖 fallback，不等於整項可刪。',
        source='啟動器與捷徑安裝明確引用此處圖片。',features='介面外觀、視窗／捷徑圖示、啟動畫面。',action='保留被程式引用的圖片；歷史版本另逐檔審閱。',evidence=['launch_msh.pyw：SPLASH_IMAGE','install_gui_shortcut.ps1：iconPath','MSH.spec：datas'],risk='required'),
    'offline_cell_analysis':item('錄影後的離線細胞分析程式','讀取既有影片、抽影格、略過模糊畫面、偵測細胞、追蹤去重、裁切與產生統計。',
        '主 GUI 不一定無法啟動，但會失去這套錄影後分析／訓練 CLI。此目錄若另放影片或模型，也必須分開保存。',
        features='離線影片分析；不是主 Tk GUI 的排版檔案。',action='功能仍要提供，程式應保留。',evidence=['offline_cell_analysis/README.md'],risk='required'),
    'firmware':item('Arduino 韌體來源','供控制板重新編譯與燒錄的程式，與 PC 上的 GUI 不同。',
        '刪除電腦上的 .ino 不會自動抹除板上已燒錄程式，GUI 可能仍可啟動；但會失去硬體韌體重建、修復與版本比對能力。',
        features='硬體維護與 PC／控制板協定一致性。',action='保留，不能因暫時不需重新燒錄就刪除。',evidence=['AGENTS.md：硬體高風險區','firmware/'],risk='required'),
    'installer':item('Windows 安裝程式配方','Inno Setup 腳本決定安裝位置、開始功能表／桌面入口與解除安裝行為。',
        '不會立刻讓已安裝 GUI 消失；但會無法按原流程產生或維護安裝檔。',features='安裝、重裝、捷徑及解除安裝流程。',action='保留。',evidence=['scripts/build_release.ps1：installer/MSH.iss'],risk='required'),
    'scripts':item('維護、診斷、進階命令與 Release 工具','包含安裝環境、資料整理、建置、打包、純應用程式稽核與診斷入口；不是同一種暫存資料。',
        '目前桌面主入口未必受影響，但會失去建置、故障排除、資料整理或既有命令列功能；不可整目錄刪除。',features='開發／維護、資料準備、進階 CLI。',action='保留正式程式；逐檔看其用途。',evidence=['README.md：Release layout','scripts/commands/','scripts/maintenance/','scripts/diagnostics/'],risk='required'),
    'tools':item('醫師標註工具與本機清理審閱工具','physician_review 是可獨立開啟的離線分類／框選／61 類 YOLO 匯出介面；release_audit 就是目前這份清單的產生器。',
        '主 MSH 視窗通常還能開，但會失去醫師工具原始 HTML 與此審閱清單的更新能力；醫師 HTML 是另一個操作介面。',features='醫師標註介面、資料匯出、本機 artifact 審閱介面。',action='保留正式工具。',evidence=['tools/physician_review/README.md','tools/release_audit/README.md'],risk='required'),
    'tests':item('軟體回歸驗證程式','核對掃描流程、模型政策、硬體訊息契約、拼接與介面 helper 的測試；測試通過不等於實體硬體驗收。',
        '日常 GUI 通常還能開，但失去重現本次 159 項通過結果與防止改壞功能的能力。',features='軟體品質驗證；不含自動取得實機驗收。',action='保留於來源。',evidence=['tests/','docs/RELEASE_LAYOUT.md'],risk='required'),
    'docs':item('操作、開發與發行說明','記錄安裝方式、硬體限制、資料分離政策、Release 檢查與歷史決策。',
        'GUI 通常仍可開，但會失去操作與維護依據；文件大小很小，刪除省不了多少容量。',features='安裝、交接、硬體限制與版本管理。',action='保留。',evidence=['docs/RELEASE_LAYOUT.md','docs/release/BUILD.md'],risk='required'),
    'licenses':item('第三方軟體的授權與聲明','記錄打包依賴的原作者授權、版權與聲明；不是套件快取。',
        '不一定立即影響 GUI，但新建置稽核會失敗，也會失去 Release 所需聲明；不能以畫面仍能開作為刪除依據。',features='合法交付、Release 稽核與來源義務追溯。',action='保留並隨發行交付。',evidence=['MSH.spec：licenses','scripts/audit_packaged_application.py'],risk='required'),
    'models':item('模型政策與歷史模型說明文件','本次此根目錄只有 README 與舊版模型說明；真正的權重在其他位置。',
        '刪除這些說明通常不會移除推論權重，但會失去模型版本與來源的解釋；不可由目錄叫 models 就認定裡面都是大模型。',features='模型政策及歷史來源文件。',action='保留小型說明文件。',evidence=['models/README.md','models/RELEASE_MODEL_v0.1.1.md']),
    'data/training':item('醫師標註與 AI 訓練資料庫','含原始血液抹片、待複核三類標註、外部參考集及少量五類白血球參考；不是程式碼，也不是自動可重建快取。',
        'GUI 的按鈕與視窗通常仍在，但指定這些資料的標註／訓練／驗證無法進行，且可能失去原始研究資料和人工整理成果。既有已訓練模型的推論不會只因訓練集移除就自動失效。',
        features='重新標註、訓練、資料核對及研究重現。',action='原檔保留；先按四個子資料用途分開審閱並核對其他備份，不能整批當訓練暫存刪除。',
        evidence=['data/training/doctor_blood_smear_20260821/README.md','scripts/prepare_doctor_blood_smear_dataset.ps1'],risk='research'),
    'reports':evidence('拼接結果的定量位置與指標報告','保存 2026-06-21 拼接位置 JSON 和量化指標摘要；不是 GUI 排版檔案。',['reports/QUANTITATIVE_METRICS_SUMMARY_20260621.md']),
    'reports/paper_training_charts':evidence('論文／研究用訓練圖表','由訓練紀錄整理的研究圖表；GUI 不靠它啟動，但投稿或研究說明可能仍引用它。',['reports/paper_training_charts/'],loss='刪除會失去這份圖表與製圖結果；只有仍持有來源 CSV、製圖程式及相同設定時才可能重建。'),
    'release':item('自動更新描述與範本','保存 latest.example.json 及相關說明，供 Release 維護時準備更新資訊。',
        '通常不會讓本機 GUI 不能開，但會失去更新發布範本；本機範本不是已發布的遠端更新檔。',features='後續版本發布與更新維護。',action='保留。',evidence=['msh_update.py','release/latest.example.json']),
    'Ultralytics':item('YOLO 本機設定與字型','本次包含 settings.json 與 Arial.ttf，用於 YOLO 套件的本機設定／文字繪製；不是白血球權重。',
        '刪設定可能重建預設值，刪字型可能改變標註文字或引發重新尋找／下載字型；離線條件下不一定成功。',features='YOLO 設定與標註文字；不是視窗按鈕位置。',action='原有未追蹤字型保留；不能為了 Git 乾淨而刪除。',evidence=['Ultralytics/settings.json、Arial.ttf','msh_runtime.py：configure_runtime_environment']),
    '__pycache__':item('根目錄 Python 編譯快取','Python 為加速匯入產生的 .pyc；原始 .py 還在時通常可以重建。',
        '程式關閉、原始碼齊全且可寫入時，清除這些快取通常只使下次啟動較慢；不能把刪除範圍擴到同層 .py 或模型。',
        features='匯入速度。',action='可列快取候選；先關閉使用中的程式，只選 __pycache__／.pyc。',evidence=['本次該群組檔案類型為 .pyc'],risk='cache'),
    'logs':evidence('來源版啟動診斷日誌','用來查 GUI 開啟失敗等問題；下次執行可產生新日誌，但舊錯誤時間與內容不會自動回來。',['launch_hardware_gui.ps1：logPath','launch_msh.pyw：SOURCE_STARTUP_LOG']),
    'dist/MSH':item('較舊的可直接執行應用程式整包','包含 MSH.exe、Python runtime、DLL 與第三方套件；舊包也含 YOLO／pylon OCR 資源，不能把每個子檔各自當垃圾。',
        '已核對的來源桌面捷徑不指向這裡；若有人從這裡開 MSH.exe，刪整包就不能開，零散刪 DLL／套件則可能只在某功能用到時才報錯。',
        installed='刪此資料夾不等於解除安裝其他位置的 MSH；但從此目錄執行的這一份就是會受影響。',features='這一份舊 EXE 的完整執行能力與回復版本。',action='確認所有捷徑／手動入口均不用且保留另一份可回復包後，可整包列候選；勿拆刪內部依賴。',evidence=['dist/MSH/MSH.exe','本次完整清單：_internal/、OCR .omc 及 YOLO 權重'],risk='review'),
    'dist/cpu':item('較早的 CPU 可攜執行包','另一份 CPU MSH.exe 與完整依賴；不是本次最新的 tmp/r1109c 候選包。',
        '不直接影響目前來源捷徑；使用這份 CPU EXE 的人會失去入口，或在內部檔案被拆刪後遇到功能錯誤。',
        installed='僅針對這份目錄內的 EXE；其他獨立安裝位置須另看。',features='歷史 CPU 包、舊版回歸與回復。',action='確認不再使用並保留可回復版本後再列候選。',evidence=['dist/cpu/MSH/','tmp/r1109c/dist/cpu/MSH/MSH-build-manifest.json']),
    'dist/release':item('歷次 Windows 安裝檔與校驗證據','多個版本的 Setup.exe、SHA-256、build manifest；舊版可能內含模型或資料，不能稱為純應用程式。',
        '刪下載用安裝檔通常不會解除安裝已安裝的 MSH，但會失去離線安裝、重裝及退版來源；安裝內容未必能只憑版本號重建。',
        features='重裝、離線交接、舊版回復與發布追溯。',action='逐版本審閱，至少保留選定可回復包及 checksum／manifest；不宜整個 dist 一起刪。',evidence=['dist/release/：版本子目錄','docs/APPLICATION_ONLY_POLICY.md']),
    'build/application-only-candidate':item('較早純應用程式來源快照','為當時候選建置複製的來源，不是目前編輯中的正式來源。',
        '來源 GUI 通常仍能用，但失去那次建置的原樣來源；尚未提交的差異不一定能從 Git 還原。',features='重建特定候選與來源對照。',action='先確認對應來源 ZIP／commit 與逐檔 hash 仍在，再列候選。',evidence=['build/application-only-candidate/：來源檔案結構']),
    'build/pyinstaller':item('PyInstaller 建置中間檔','分析表、封裝中間檔與快取，供把 Python 打包成 EXE；不是日常 GUI 主程式。',
        '非建置中且正式來源完整時，可重新建置產生；刪除通常不影響來源 GUI／既有安裝包，但下次打包耗時增加並失去舊建置診斷。',features='建置速度與建置失敗診斷。',action='確認沒有正在打包後可列重建型候選。',evidence=['scripts/build_release.ps1：workPath'],risk='cache'),
    'build/ultralytics':item('建置時的 YOLO 隔離設定','MSH.spec 指定給建置過程的設定目錄，避免污染一般使用者設定。',
        '非建置中時通常會於下次建立；仍會失去當時建置設定，勿把它與真正訓練輸出混在一起。',features='打包過程的設定隔離。',action='完成建置後可列重建型候選。',evidence=['MSH.spec：YOLO_BUILD_CONFIG'],risk='cache'),
    'tmp':evidence('暫存根層的腳本、封存包與工作證據','這一列只計 tmp 直屬檔案，子目錄另列。名稱 tmp 不保證內容可丟棄，可能含測試腳本、ZIP、交接清單或本機設定。',['本次 files.jsonl：group=tmp'],loss='刪整個 tmp 會連同其他列中的模型、研究影像、USB 交接備份及候選包一起刪掉；必須逐檔／子目錄選定。'),
    'stitched_output/stitched_output/stitched_output/cell_identification':item('辨識程式搬移後的歷史殘留目錄','本次檔案清單在這裡只見 .pyc 快取；正式來源已在 msh_app/cell_identification。',
        '若仍僅含列出的 .pyc，移除快取通常不影響新版來源 GUI；不能據此推論整個 stitched_output 都可刪。',features='歷史 Python 快取。',action='僅把已確認的 .pyc 列快取候選；遇到其他檔案需重新分類。',evidence=['files.jsonl：此群組 .pyc','launch_msh.pyw：GUI_SCRIPT'],risk='cache'),
    'stitched_output/stitched_output/stitched_output/hardware':item('歷史硬體設定與快取混合目錄','目前有 .pyc 與 camera_profiles/ 下設備專用 .pfs；前者可重建，後者是實體相機設定。',
        '清快取與刪相機 profile 後果完全不同；刪 .pfs 可能失去該設備的取像設定與回復依據，即使視窗還能開也可能影響取像結果。',
        features='相機設定保存與硬體維護。',action='相機 profile 保留並另備份；只可分開審閱 .pyc。禁止整個目錄清除。',evidence=['hardware/camera_profiles/*.pfs','AGENTS.md：Basler camera profile 保留規則'],risk='research'),
    'stitched_output/stitched_output/stitched_output/models':item('仍在原位置的歷史 WBC 偵測權重','保存 wbc_focus_yolov8n_e_20260611.pt；歷史身分記錄為 WBC 單類偵測，不是 61 類分類模型。',
        'GUI 版面仍可存在，但選用此權重的白血球偵測會因缺檔失敗；有相同 hash 的 demo_start.pt 也不會自動替換原路徑。',
        features='以這份本機模型進行 WBC 定位、歷史結果重現。',action='原件保留；先核對實際選用位置、備份與路徑遷移，再考慮重複副本。',evidence=['msh_release_model.py：RELEASE_MODEL_SHA256／CLASSES','msh_app/cell_identification/object_detection.py：resolve_detect_model_path'],risk='research'),
}

# Specific roles were checked against the named local reports, not inferred from "tmp".
TEMP = {
 'application_only_clean_source':('舊純來源交接快照','當時排除資料／模型的程式副本，供建置或交接比對。','README.md／MSH.spec 等來源結構'),
 'b014':('早期 v0.1.4 建置快照與執行包','含當時來源、EXE 和候選安裝產物；不是目前編輯來源。','dist/、MSH.spec'),
 'b014app':('安裝測試留下的保留哨兵','user-retention.txt 用來測安裝／解除安裝是否保留使用者資料；不是實際使用者文件的替代備份。','user-retention.txt'),
 'b014user':('安裝測試的隔離使用者目錄','Documents/MSH 與 AppData 下的 retention 檔用來核對使用者資料不被清掉。','Documents/MSH/retention.txt'),
 'drive_audit_20261019':('2026-10-19 硬碟／交接盤點紀錄','記錄當時模型、實驗與歷史備份比對；不是被盤點原資料本身，也不證明那些備份現在仍存在。','historical_backup_comparison.json、local_artifact_comparison.json'),
 'frozen014check':('舊版封裝 EXE 的驗證副本','獨立 EXE 與依賴，用來測 frozen 狀態；刪除會失去重跑該副本的能力。','MSH-build-manifest.json、MSH.exe'),
 'i1109':('前一階段已整合來源的 CPU 候選包','2026-11-09 整合階段來源、完整 EXE 與安裝檔；曾做隔離安裝／重裝／解除安裝驗證。','../integrated-candidate-20261109/VALIDATION.md'),
 'install014':('使用者檔案保留測試殘留','user-retention.txt 和 sentinel.pt 是測試哨兵；副檔名 pt 不代表可用的 AI 模型。','user-models/sentinel.pt'),
 'integrated-candidate-20261109':('前一階段整合與安裝驗證證據','保存來源 ZIP、瀏覽器回歸結果、payload 稽核、隔離 GUI／模型測試及 Git 交付紀錄；也含完整 probe 副本。','VALIDATION.md、payload-audit-final.json'),
 'lic014-native-source-evidence':('原生依賴的來源／建置證據','收集原生 runtime 的來源線索和建置腳本；不只是下載快取。','NATIVE_SOURCE_EVIDENCE.json'),
 'lic014-notices-followup':('第三方授權補查結果','第三方 LICENSE 與補查說明；正式 licenses/ 是否完整對應需另核對。','README.md、third_party/'),
 'lic014-upstream-sources':('上游來源下載清單','記錄需交付／核對的第三方來源套件；清單不等於套件內容或已完成來源交付。','SOURCE_DOWNLOADS.json'),
 'lic014-upstream-sources-network':('已下載的部分第三方來源封存包','包含多個 tar.gz 與下載清單，用於來源交付查核；非 MSH 模型資料。','SOURCE_DOWNLOADS.json、*.tar.gz'),
 'lic014app':('授權階段安裝測試哨兵','只留下 user-retention.txt，供驗證安裝流程不刪使用者檔案。','user-retention.txt'),
 'lic014probe':('授權檢查階段的封裝測試副本','完整 MSH.exe 與依賴，用來核對當時加入的授權及 runtime。','MSH-build-manifest.json、_internal/licenses/'),
 'lic014user':('授權階段的隔離使用者設定／日誌','保留 retention 哨兵、啟動記錄及 YOLO 設定；不是日常使用者的正式 Documents。','retention.txt、msh.log'),
 'migrate014':('v0.1.3→v0.1.4 遷移測試與舊資料備份','保存新舊安裝／解除安裝日誌、備份核對與舊 runtime 資源；裡面也有模型，不應當作純 cache。','verification.json、backup-verification.json'),
 'model_method_audit_20261021':('模型訓練方式的歷史稽核','保存權重 metadata 的安全解析結果、與訓練 CSV 比對和流程說明；其中引用外部硬碟路徑不表示這裡存有全部模型。','checkpoint_metadata.json、consistency_checks.json'),
 'msh014-audit-fixture':('封裝稽核的合成測試樣本','小型假 app/source 檔驗證稽核能擋掉禁止資源；這裡叫 MSH.exe 的檔案不保證是真正可執行程式。','app/、source/ 測試結構'),
 'msh014-collision-guard':('禁止覆寫既有安裝檔的測試樣本','用哨兵安裝檔和最小來源，驗證建置工具拒絕覆蓋同名產物。','dist/release/v0.1.4/、scripts/build_release.ps1'),
 'msh014-frozen-validation':('早期 EXE 啟動驗證日誌','保存 exit/process JSON 及隔離 profile 日誌；未包含完整主程式。','exit.json、process.json'),
 'msh014-frozen-validation-b':('第二次封裝推論／訓練煙霧測試','含合成圖片、合成標註、小型訓練輸出與權重，驗證流程可跑，不證明白血球準確率。','verification.json、synthetic.yaml、train-smoke/'),
 'msh014-frozen-validation-c':('第三次封裝推論／訓練煙霧測試','另一輪隔離測試的合成資料與結果；不能把它當正式訓練成果。','verification.json、synthetic.yaml、train-smoke/'),
 'msh014-install-user':('安裝測試的隔離 Windows 使用者目錄','含測試 Documents、AppData、保留哨兵及 Windows 圖示快取；不同於真正使用者目錄。','retention.txt、iconcache_*.db'),
 'msh014-model-validation':('模型載入／微型訓練的合成驗證','合成影像、YOLO 設定與 best/last 測試權重；供功能煙霧測試，不是研究模型。','verification.json、synthetic.yaml、train-smoke/'),
 'msh_training_recording_demo_20261021':('訓練教學／錄影示範成果','包含從歷史影像標註準備的示範資料、單類及 61 類示範 run、best/last 權重和起始模型；不是全部合成資料，也不是原始歷史訓練。','demo_manifest.json：historical candidate labels；latest_run.json：teaching demonstration'),
 'physician':('醫師離線標註工具的開發／瀏覽器測試目錄','有 app.js、產生 HTML 的程式、回歸測試與截圖；正式可交付 HTML 在 tools/physician_review。','app.js、build.py、check_*.cjs'),
 'physician_yolo_validation':('醫師工具 YOLO 匯出的跨瀏覽器測試','保存 Chrome／Edge 的合成匯出 ZIP、獨立格式／座標驗證及截圖。','independent_zip_validation.json、ultralytics_loader_validation.json'),
 'pub014build':('開源／授權整理階段的候選建置','當時來源與 CPU 候選包，供對照授權聲明；不是已發布正式 Release 的證明。','MSH.spec、dist/'),
 'public014src':('開源準備階段的純來源快照','含當時程式、文件與授權資訊；可能與目前未提交工作樹不同。','README.md、LICENSE、THIRD_PARTY_NOTICES.md'),
 'push_validation_20261109':('推送前醫師工具的回歸證據','保存合成 YOLO 匯出 ZIP、預期結果及工具截圖，供已提交功能的回歸核對。','chrome/expected.json、synthetic_yolo_export.zip'),
 'r1109c':('本次目錄整理後的最終候選來源與執行包','保存本次來源快照、可直接啟動的 CPU EXE 與候選安裝檔；前一階段提供的安裝檔連結就在這裡。','dist/cpu/MSH/MSH-build-manifest.json、dist/release/v0.1.4/'),
 'rc014b':('更早的 v0.1.4 CPU 候選建置','較早來源快照、EXE 與安裝檔；仍可能供歷史回歸或回復使用。','MSH.spec、dist/'),
 'usb_latest_20261019':('A／B 地交接與離線回復備份','含多分支來源 ZIP、Git bundle／離線歷史、醫師工具、模型、影像訓練資料、舊安裝包與交接清單。約 9.38 GiB 並非單純暫存。','USB_TRANSFER_VERIFICATION.json、package/TRANSFER_MANIFEST.json、offline_restore_check.git/'),
 'video_review_20261021':('教學錄影檢閱用影格與接觸表','從錄影截出的 contact_*.jpg 與 frame_*.png，用來檢查示範內容；不是錄影原檔。','contact_*.jpg、frame_*.png'),
}

for name,(title,purpose,proof) in TEMP.items():
    GROUPS['tmp/'+name]=evidence(title,purpose,['tmp/'+name+'/'+proof])

for name in ('application_only_clean_source','b014','frozen014check','i1109','lic014probe','pub014build','public014src','rc014b'):
    GROUPS['tmp/'+name]['deletion_effect']='目前來源桌面捷徑不直接使用此副本；但若手動執行這裡的 EXE／腳本就會失效，也會失去該次來源或可回復版本。尚未確認所有外部引用。'

GROUPS['tmp/r1109c'].update(risk='required',action='本次候選仍待驗收，請保留。完成正式交付並另有可回復包後才重新審閱。',
    deletion_effect='日常來源 GUI 不一定受影響，但目前提供的候選安裝檔與可攜 EXE 連結將失效，亦無法在原位置繼續驗收。')
for name in ('usb_latest_20261019','msh_training_recording_demo_20261021','migrate014'):
    GROUPS['tmp/'+name].update(risk='research',action='分開核對模型、影像、資料及備份；未確認另一份完整可用副本前保留。',
        deletion_effect='通常不直接改變目前來源 GUI，但會失去此處的模型、資料、歷史成果或回復能力；若有流程指向這些路徑，該流程會缺檔失敗。')
GROUPS['tmp/usb_latest_20261019']['certainty']='已讀交接 manifest，記載 2026-10-19 曾核對外部交接副本；尚未重新驗證該外部副本現在仍完整可用。'

for name,title,purpose,loss in (
 ('README.md','專案使用說明','介紹專案入口、功能、安裝及資料政策。','GUI 通常仍能開，但會失去主要操作與交接說明。'),
 ('AGENTS.md','專案作業安全規則','記錄 Git、模型資料保存與硬體操作限制；不控制 GUI 排版。','程式通常仍能執行，但後續開發會失去這份安全與授權邊界。'),
 ('LICENSE','第一方程式授權','宣告正式程式來源所採用授權；不是可省容量的 runtime。','GUI 可能還能開，但打包稽核與正確發行會缺少必要授權。'),
 ('THIRD_PARTY_NOTICES.md','第三方聲明總表','整理依賴、版權及來源義務，連結各套件聲明。','GUI 可能還能開，但 Release 稽核及交付所需聲明不完整。'),
 ('.gitignore','本機資料不進 Git 的規則','排除模型、研究資料、環境、建置與暫存，避免誤提交。','不直接改變 GUI，但未來大量本機或研究資料可能出現在 Git 待加入清單。'),
 ('.gitattributes','Git 檔案／換行處理規則','讓不同機器對來源換行與檔案類型採一致處理。','不一定影響當下 GUI，但跨機提交與檔案內容比對可能改變。'),
 ('.cell_project_install.json','這台電腦的開發環境安裝紀錄','記錄既有環境路徑，供 install/update 腳本使用；不是 GUI 原始碼。','目前捷徑不一定壞，但更新腳本可能找不到原環境設定；不能當作一般可重建 cache。'),
 ('serpentine_recording.py','蛇形掃描錄影的相容 CLI','根目錄小入口轉交 cell_stitching_project 中的錄影流程。','主 GUI 不一定受影響，既有根目錄命令會因入口缺失而失效。'),
 ('wbc_serpentine_capture.py','白血球蛇形擷取的相容 CLI','把舊命令導向套件內的白血球掃描／擷取功能。','主 GUI 不一定受影響，但既有 CLI 或外部腳本可能找不到入口。'),
):
    GROUPS[name]=item(title,purpose,loss,action='保留於正式來源／本機設定；不是優先瘦身對象。',evidence=[name],risk='required')

for name,what in (
 ('requirements.txt','來源版主要功能依賴'),('requirements-build.txt','PyInstaller／建置依賴'),
 ('requirements-cpu.txt','CPU 推論／訓練依賴'),('requirements-gpu.txt','GPU 開發依賴'),
 ('requirements-release-v0.1.4.txt','v0.1.4 已記錄的發行環境版本'),
):
    GROUPS[name]=item(what+'清單','這是安裝／重建套件的文字配方，不是套件本身。',
        '刪清單不會同時移除已安裝套件，GUI 可能仍能開；但新機重建、問題重現及 Release 驗證失去依據。',
        features='環境重建與交接。',action='保留，容量極小。',evidence=[name],risk='required')

ROLES = {
 'unknown-file':item('單檔用途仍待核對','此筆屬於下方群組，但目前未取得足夠的單檔引用／格式資訊。','不能把整個群組的刪除後果直接當作這一個檔案的結果；也不能宣稱無影響。',features='需依檔案內容、建立流程及引用位置再判讀。',action='保留待確認，先看下方群組用途。',risk='unknown',certainty='單檔用途未確認。'),
 'documentation':item('操作、開發或套件說明文字','README／Markdown／說明文字；可用來了解上層工具、資料來源或依賴。','通常不直接改變按鈕，但會失去說明或來源依據；授權／資料字典等特殊文字須按實際檔案用途另外保存。',features='操作與來源說明。',action='通常很小，建議保留；不能一律把文字檔當作無用。',risk='review'),
 'source-code':item('Python 功能原始碼','此檔定義功能或命令入口；具體功能請結合下方群組說明。未針對這一檔建立完整呼叫圖。','被啟動器或功能載入時會缺模組／函式，可能啟動失敗，也可能直到使用功能才失敗。',features='所屬套件／工具的程式功能；不是研究資料或快取。',action='保留正式來源；若是歷史快照，評估整份副本而非拆刪程式。',risk='required'),
 'command':item('PowerShell／批次命令入口','把安裝、資料整理、訓練、診斷或建置步驟串接起來；實際用途以所屬工具為準。','通常不改變已開啟的主視窗，但執行這個入口的捷徑／維護流程會失效；沒有逐一排除外部引用。',features='進階 CLI、診斷、維護或建置。',action='正式工具保留；歷史副本與整包一同審閱。',risk='required'),
 'executable':item('這一份應用程式的執行入口','MSH.exe 會開啟它所屬目錄的那份介面，並依賴同包的 runtime。','這份 EXE 及指向它的捷徑將無法啟動；另一份來源版／安裝版是否仍可用須分別看路徑。',features='這一份應用程式的 GUI 與離線工作。',action='使用中或待驗收版本保留；不用的歷史包須整包審閱。',risk='required'),
 'font':item('字型資源','提供介面或影像標註的文字字形；不是模型權重。','可能缺字、改變標註外觀或使套件重新尋找／下載字型；離線時未必能補回。',features='顯示文字與繪製標籤。',action='保留正在使用的字型；歷史包內副本隨整包審閱。',risk='required'),
 'branding':item('圖示／圖片資源','位於應用程式資源路徑；可用作圖示、品牌圖或套件的顯示資源，不是由副檔名就能判定的研究原圖。','可能缺圖、缺啟動畫面，或某些安裝／繪圖步驟報缺檔；具體引用需看上層位置。',features='外觀或圖片資源載入。',action='正式引用的資源保留；舊包內副本隨整包審閱。',risk='required'),
 'cache':item('Python／工具可重建快取','這一筆是快取，不等於上層整個目錄可刪。','有完整來源且非執行／建置中時通常能重建；下次匯入或資料掃描較慢。',features='執行速度；資料掃描快取仍需原始資料。',action='可列候選，只選這筆快取，勿擴及相鄰資料。',risk='cache',certainty='依副檔名／明確快取路徑辨識；不保證上層其他檔案安全。'),
 'camera-profile':item('設備專用 Basler 相機設定','保存特定相機的 profile；不是一般圖片或 GUI 圖示。','介面可能仍能開，但失去既有取像設定與還原依據；影像外觀與設備行為可能不同。',features='相機取像及設備設定還原。',action='保留並另備份；不修改設定值。',evidence=['AGENTS.md：camera profile 高風險區'],risk='research'),
 'firmware':GROUPS['firmware'],
 'library':item('這份環境／執行包的函式庫或原生 runtime','Python、DLL、PYD 等檔案共同組成一份環境；單看名字無法確定哪個延後使用的功能會載入它。','零散刪除可能使 GUI 無法開，或直到拼接、偵測、相機等功能被使用時才失敗。',source='若檔案位於目前 .venv312 或正式來源，其刪除可影響來源 GUI；位於舊包則影響那一份副本。',installed='若位於某份 EXE 的 _internal 內，就可能是那份 EXE 所需；不能以「已經是 EXE」推論不需要 DLL／Python 套件。',features='依所屬套件而定；未逐一做移除測試。',action='勿拆刪。若不再使用，先核對上層整份環境／舊包再整包審閱。',risk='required',certainty='依套件／runtime 路徑及檔案類型辨識；單一檔案用途未全面逆向分析。'),
 'image':item('影像資料或圖像輸出','若在研究目錄，可能是原圖、裁切、標註疊圖或訓練圖表；相同副檔名不表示用途相同。','介面通常仍能開，但這筆影像與其訓練／標註／重現價值會消失；只有持有原始輸入及方法才能談重建。',features='依上層資料用途；研究影像不得當作 GUI 圖示快取。',action='依上層說明及 provenance 核對，未確認備份前保留。',risk='research',certainty='僅由目錄／副檔名判斷；未讀取影像像素或確認病人／玻片身分。'),
 'label':item('人工／YOLO 標註或類別對照','labels/、annotations 或 classes 檔案把影像轉成訓練標籤；不是可從影像無損自動產生的文字垃圾。','視窗仍可開，但會失去框、類別或人工檢閱成果，訓練／還原標註可能缺資料或錯配。',features='醫師標註、YOLO 訓練、類別 ID 一致性。',action='與對應影像、類別表及來源清單一起保存。',risk='research'),
 'best':item('這次訓練選出的 best 權重','通常是該次 run 依驗證指標挑出的 checkpoint；名稱 best 不代表已證明是所有模型中最好或已獲研究驗收。','GUI 仍可存在，但選此模型推論或重現該次訓練會缺檔；不能把同目錄 last 自動當成完全相同替代。',features='這次 run 的模型推論／重現。',action='核對 run、資料、實際使用位置與備份後再審閱。',risk='research',certainty='依訓練 run 路徑及常見 checkpoint 命名判讀；未載入權重或驗證準確率。'),
 'last':item('這次訓練最後保存的 last 權重','保存 run 最後一輪的 checkpoint；可能用於接續或重現，與 best 不一定相同。','GUI 仍可開，但接續／重現該 checkpoint 會缺檔；是否真的可 resume 還需核對其中訓練狀態。',features='訓練延續、最後狀態與結果對照。',action='不要只因有 best 就刪 last；先核對用途與備份。',risk='research',certainty='依命名及 run 結構判讀；未載入權重，未證明可 resume。'),
 'ocr':item('舊 pylon 套件附帶的 OCR 字型模型','位於 pypylon/pylonDataProcessingPlugins/.../ocr/ 的 .omc；是文字辨識資源，不是你的白血球訓練權重。','不會刪掉白血球訓練成果，但拆刪這份舊包的資源可能使其 OCR/plugin 功能失效；不能由新版排除它就推論舊包拆刪安全。',source='目前來源桌面捷徑不直接讀取這份舊包的 OCR 檔。',installed='影響它所屬的舊 EXE／SDK 副本；其他安裝位置另外判斷。',features='第三方文字辨識 plugin；不是白血球類別辨識。',action='把它和整份舊 runtime 一起評估，勿當研究模型逐份保留或零散清除。',evidence=['檔案完整路徑包含 pypylon/pylonDataProcessingPlugins/.../ocr/'],risk='review',certainty='依第三方套件與 ocr 路徑分類；未逆向解析 .omc。'),
 'focus':item('歷史 WBC 單類偵測模型','此檔名對應舊版記錄的白血球定位模型；只有 hash 相符時才能確認是同一份歷史權重。','刪檔通常不刪除按鈕／版面，但所有指定此路徑的 WBC 推論會缺檔。相同 hash 副本也不會自動修正原本的選取路徑。',features='WBC 單類定位；與 61 類新資料的類別定義不同。',action='保留原件與至少一份經核對備份，先確認使用路徑。',evidence=['msh_release_model.py：歷史檔名／hash／WBC 類別'],risk='research',certainty='依歷史身分記錄；未在本次重新評估模型準確率。'),
 'base-model':item('一般 YOLO 基底／示範權重','yolov8n.pt 常供初始化或示範；單靠檔名不能證明它是專案的白血球訓練成果。','GUI 通常仍可開；指定此檔的基底訓練或推論會缺檔。本專案要求本機模型，不能假設刪掉後一定自動下載補回。',features='以這份權重初始化訓練／推論的流程。',action='先核對 hash、來源及使用腳本；勿只靠檔名推論可重下載。',evidence=['msh_model_policy.py：require_local_model'],risk='research',certainty='依檔名及本機模型政策判讀；不宣稱已確認類別或權重來源。'),
 'synthetic-model':item('合成資料／未訓練模型的測試權重','位於 synthetic／train-smoke 等隔離測試流程，用來驗證載入與匯出，並不是研究準確率的證明。','一般 GUI 不需它；刪除後該次模型測試／回歸腳本會缺樣本，仍應保存驗證紀錄與可重建方法。',features='軟體模型載入、微型訓練及封裝測試。',action='核對對應 verification／產生腳本後列測試候選；不要移除同名研究模型。',risk='review',certainty='依明確測試路徑與既有驗證文件；未載入權重。'),
 'archive':item('交接／來源／資料封存檔','ZIP、bundle 等容器；裡面可能有程式，也可能有模型、影像、Git 歷史或人工結果，不能只看外層副檔名。','GUI 不一定受影響，但可能失去唯一備份、舊版回復或離線交接來源；未核對內容及另一份副本前不能認定可重建。',features='備份、離線交接、歷史回復。',action='依上層 manifest 核對內容、hash 與另一份完整可用副本。',risk='review'),
 'setup':item('Windows 安裝程式','Setup.exe 用來把特定版本安裝到指定位置；不是目前正在編輯的 GUI 原始碼。','刪安裝檔通常不解除安裝已裝好的程式，但會失去離線重裝／退版來源；若同名只是測試哨兵，要看上層測試說明。',features='安裝、重裝與版本回復。',action='至少保留選定版本及其 SHA-256／build manifest；先核對是否已交付。',risk='review'),
 'manifest':item('清單、校驗或驗證紀錄','記錄來源、hash、版本、類別或測試結果；有些也是程式會讀的必要設定，須以完整路徑及上層用途為準。','刪除會失去追溯、校驗或資料對照能力；若是執行設定還會讓相應流程缺檔。',features='來源追溯、資料一致性、版本／測試證據。',action='通常很小，先保留；不能只因是 JSON／CSV 就當快取。',risk='review'),
}

DATA_PARTS = {
 '01_raw_blood_smear_images_to_annotate':('待醫師標註的原始抹片影像','原始顯微鏡畫面；不是偵測框疊圖，也不是可以由模型還原的資料。','刪除會失去原圖，未來重新標註、裁切或研究重現可能無法完成。'),
 '02_yolo_3cls_existing_labels_review_required':('待複核的 WBC／RBC／Platelets 三類資料','既有 YOLO 影像與標註，仍需醫師逐框檢查；不是已完成新簽核的 ground truth。','刪除會失去三類訓練素材、標註及整理成果；現有模型推論通常仍可開，但不能重新訓練／重現。'),
 '03_external_txl_pbc_reference_license_review':('外部來源的血球參考集','外部參考資料；文件要求另核對使用與散布條件，不是專案自行拍攝來源。','GUI 通常不受直接影響，但失去外部比較／參考資料；是否能再取得同版本尚未核對。'),
 '04_wbc5_reference_smoke_only':('五類白血球少量參考樣本','供格式與流程示範的少量五類參考；不代表已足夠做完整模型訓練／效能驗證。','刪除會失去這份參考／測試素材；通常不會讓一般 GUI 無法開啟。'),
}

GROUPS['yolov8n.pt']=deepcopy(ROLES['base-model'])
for checkpoint in ('best','last'):
    ROLES[checkpoint+'61']=deepcopy(ROLES[checkpoint])
    ROLES[checkpoint+'61'].update(title='61 類教學 run 的 '+checkpoint+' 權重',
        purpose=ROLES[checkpoint]['purpose']+' 所在 runs61 是後續教學訓練，資料定義 61 類，不代表每類有足量樣本或已通過模型效能驗收。',
        evidence=['tmp/msh_training_recording_demo_20261021/latest_run.json','tools/physician_review/README.md：61 類匯出'])
    ROLES[checkpoint+'-teaching']=deepcopy(ROLES[checkpoint])
    ROLES[checkpoint+'-teaching'].update(title='單類教學微調 run 的 '+checkpoint+' 權重',
        purpose=ROLES[checkpoint]['purpose']+' 所在 teaching run 使用少量歷史候選標註做後續教學微調；不是重新完成的醫師簽核，也不是原始歷史訓練。',
        evidence=['tmp/msh_training_recording_demo_20261021/demo_manifest.json'])


def group_explanation(path):
    return deepcopy(GROUPS.get(path) or item('用途尚未完成核對的項目',
        '目前只有檔名、容量與類別，尚無足夠證據判斷確切用途。',
        '無法排除程式、研究資料或個人流程仍會使用，不能宣稱刪除不影響。',
        action='保留並待確認；需要找建立它的文件／腳本或使用者說明。',risk='unknown',certainty='未確認；不從名稱猜測可刪除。'))


def file_role(path):
    p=PurePosixPath(path);parts=p.parts;name=p.name.lower();suffix=p.suffix.lower()
    if '__pycache__' in parts or suffix in {'.pyc','.pyo'} or name in {'train.cache','val.cache'}:return 'cache'
    if suffix=='.pfs':return 'camera-profile'
    if suffix=='.ino':return 'firmware'
    if suffix=='.omc' and 'ocr' in parts and 'pypylon' in parts:return 'ocr'
    if name=='synthetic_61class_untrained.pt' or ('train-smoke' in parts and suffix in {'.pt','.pth'}):return 'synthetic-model'
    if name in {'best.pt','last.pt'}:
        base=p.stem.lower()
        if 'runs61' in parts:return base+'61'
        if any(part.startswith('teaching_') for part in parts):return base+'-teaching'
        return base
    if name in {'wbc_focus_yolov8n_e_20260611.pt','demo_start.pt'}:return 'focus'
    if name=='yolov8n.pt':return 'base-model'
    if suffix in {'.dll','.pyd','.so'} or name=='base_library.zip' or ('_internal' in parts and suffix in {'.py','.pyw'}) or (parts[0].startswith(('.venv','.conda')) and suffix in {'.py','.pyw'}):return 'library'
    if name=='msh.exe':return 'executable'
    if suffix in {'.ttf','.otf'}:return 'font'
    if suffix in {'.bat','.ps1'}:return 'command'
    if suffix in {'.py','.pyw'}:return 'source-code'
    if name.startswith('msh_setup_') and suffix=='.exe':return 'setup'
    if suffix in {'.zip','.bundle','.gz','.7z'}:return 'archive'
    if 'labels' in parts or name in {'classes.txt','class_mapping.json','annotations.json'}:return 'label'
    if suffix in {'.png','.jpg','.jpeg','.bmp','.tif','.tiff','.dcm','.svs'} and 'assets' not in parts:return 'image'
    if suffix in {'.png','.jpg','.jpeg','.ico'} and 'assets' in parts:return 'branding'
    if suffix in {'.md','.rst'}:return 'documentation'
    if suffix in {'.sha256','.json','.jsonl','.csv','.yaml','.yml'}:return 'manifest'
    return ''


def explain_file(path,group):
    """Used by tests and Markdown output; HTML combines the same shared records."""
    parent=group_explanation(group)
    role=file_role(path)
    detail=None if path==group else deepcopy(ROLES.get(role) or ROLES['unknown-file'])
    for part,(title,purpose,loss) in DATA_PARTS.items():
        if part in PurePosixPath(path).parts:
            detail=item(title,purpose,loss,features='研究資料與訓練素材；獨立已訓練模型不靠此檔案開啟 GUI。',
                        action='先保留並核對備份及對應標註。',evidence=['data/training/doctor_blood_smear_20260821/README.md'],risk='research')
            break
    return parent,detail


def add_explanations(report):
    report['explanations']={'groups':GROUPS,'roles':ROLES,'data_parts':DATA_PARTS,
        'default':group_explanation('__unknown__')}
    report['explanation_scope']='依來源引用、檔案結構及既有本機報告判讀。未逐項刪除實驗；無法排除個人設定／外部腳本引用。'
    report['model_types']={'third_party_ocr':sum(file_role(m['path'])=='ocr' for m in report['models']),
                           'pytorch_checkpoints':sum(PurePosixPath(m['path']).suffix.lower() in {'.pt','.pth'} for m in report['models'])}
    for group in report['groups']:
        group['explanation_key']=group['path']
    for model in report['models']:
        model['role']=file_role(model['path'])
    return report
