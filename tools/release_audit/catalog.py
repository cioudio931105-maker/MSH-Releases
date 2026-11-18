"""Render a local metadata review artifact. No network or file deletion actions."""
from pathlib import Path
import json
from tools.release_audit.explanations import add_explanations, explain_file, group_explanation


def write_catalog(report: dict, output: Path) -> Path:
    add_explanations(report)
    payload = json.dumps(report, ensure_ascii=False).replace('<', '\\u003c').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    template = Path(__file__).with_name('catalog.html').read_text(encoding='utf-8')
    destination = output / 'index.html'
    destination.write_text(template.replace('/*__INVENTORY__*/null', payload), encoding='utf-8')
    write_item_guide(report,output)
    return destination


def write_item_guide(report: dict, output: Path) -> Path:
    """A readable companion for the same group/model explanations in the HTML."""
    lines=['# MSH 每項用途與刪除影響說明','',
        '本說明沒有刪除、搬移或上傳檔案，也沒有載入模型或實做逐項刪除實驗。',
        '來源版與獨立安裝版必須分別判斷；視窗仍能開，不代表偵測、訓練、標註、回復與交接都不受影響。',
        '以下涵蓋全部資料群組與權重副檔名項目；完整檔案模式另依檔案類型補充。用途未明的單檔仍標為待確認。','',
        f"盤點：{report['created']}；{len(report['groups'])} 個資料群組，{len(report['models'])} 份權重副檔名檔案。",
        f"其中 {report['model_types']['third_party_ocr']} 份為舊 pylon OCR 資源，{report['model_types']['pytorch_checkpoints']} 份為 PT checkpoint／測試檔；並非全是白血球訓練成果。",'']
    fields=[('用途','purpose'),('來源版介面','source_gui'),('獨立安裝版','installed_gui'),
            ('涉及功能','features'),('刪除後果','deletion_effect'),('建議','action'),('判斷限制','certainty')]
    def section(path,spec,level='##'):
        lines.extend([f'{level} {path}','',spec['title'],''])
        lines.extend(f'- {label}：{spec[key]}' for label,key in fields)
        lines.append('- 依據：'+'；'.join(spec['evidence'] or ['依檔案類型與所屬群組判讀，未取得更細引用。']))
        lines.append('')
    for record in sorted(report['groups'],key=lambda r:r['path']):
        section(record['path'],group_explanation(record['path']))
        if record['path']=='data/training':
            for part,(title,purpose,loss) in report['explanations']['data_parts'].items():
                lines.extend([f'### {title}',f'- 子目錄：{part}',f'- 用途：{purpose}',f'- 刪除後果：{loss}',''])
    lines.extend(['# 權重副檔名項目逐筆說明','',
        '每項仍須結合其所屬資料群組；舊執行包的副本與原件不是同一個使用路徑。',''])
    for model in sorted(report['models'],key=lambda r:r['path']):
        parent,detail=explain_file(model['path'],model['group'])
        section(model['path'],detail or parent)
        lines.append('- 所屬群組：'+model['group']+'；'+parent['purpose'])
        lines.append('- SHA-256：'+model.get('sha256','本份未核對；不能只依檔名／大小確認身分或重複。'))
        peers=[p for group in report['verified_model_duplicates'] if model['path'] in group['paths'] for p in group['paths'] if p!=model['path']]
        if peers:lines.append('- 已核對相同內容：'+'；'.join(peers)+'；不會自動替換原路徑，不代表已授權刪除。')
        lines.append('')
    destination=output/'ITEM_GUIDE.md'
    destination.write_text('\n'.join(lines),encoding='utf-8')
    return destination
