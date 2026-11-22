"""Export public demonstration episodes and actual isolated-policy trajectories."""
import json
import os
import re
import shutil
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
os.environ['PYTHONPATH']=str(ROOT/'src')+os.pathsep+os.environ.get('PYTHONPATH','')
from sled.generation import generate
from sled.runner import run_episode
from sled.validation import verify_episode
from sled.storage import write_json
from web_comparison import comparison

SINGLE_ISSUE = dict(invoice_count=14, duplicate_count=0, allocation_count=0,
                    fx_count=0, cutoff_count=0, interaction=False)

def main():
    definitions=[
        ('fx-period','Валюта и граница периода','Валютный платёж отражён по прежнему курсу и попал в следующий месяц.','bank','manual_fx_period.json',None),
        ('duplicates','Дубль и распределение','Счёт признан дважды, а часть полученного платежа осталась нераспределённой.','layers','manual_errors.json',None),
        ('clean','Чистая компания','Счёт на 1 000 KZT оплачен на 600 KZT. Остаток 400 KZT — законная задолженность.','shield','manual_clean.json',None),
        ('generated','Сгенерированная компания','Все четыре типа ошибок, разбитые оплаты и корректные отвлекающие случаи.','database',None,(20261119,{})),
        ('duplicate-only','Повторный счёт','Один первичный счёт признан в книге дважды.','layers',None,(20261120,SINGLE_ISSUE | {'duplicate_count':1})),
        ('unallocated','Незачтённый платёж','Деньги получены, но платёж целиком остался нераспределённым.','wallet',None,(20261121,SINGLE_ISSUE | {'allocation_count':1,'allocation_mode':'missing'})),
        ('fx-date','Курс за другой день','Курс взят за соседний день вместо даты первичного платежа.','bank',None,(20261122,SINGLE_ISSUE | {'fx_count':1,'fx_mode':'date'})),
        ('invoice-cutoff','Счёт на границе периода','Счёт выставлен в текущем периоде, но начисление попало в следующий.','receipt',None,(20261123,SINGLE_ISSUE | {'cutoff_count':1,'cutoff_target':'invoice'})),
        ('clean-refunds','Возвраты без нарушений','Разбитые платежи, возвраты и операции без привязки к счёту учтены корректно.','shield',None,(20261124,SINGLE_ISSUE | {'split_count':3,'refund_count':2,'null_count':2})),
        ('kwd-offset','Валюты и часовой пояс','Три десятичных знака в базовой валюте и другой часовой пояс компании.','database',None,(20261125,{'invoice_count':18,'base_currency':'KWD','period_start':'2026-12-01T00:00:00-07:00','rounding':'ROUND_HALF_UP','fx_mode':'date'})),
    ]
    cases=[]
    for slug,title,description,symbol,fixture,generated in definitions:
        episode=json.loads((ROOT/'fixtures'/fixture).read_text()) if fixture else generate(*generated)
        verify_episode(episode)
        result=run_episode(episode,'reconciler','evaluation')
        assert not result['truncated'] and result['evaluation']['f1']==1
        metrics={k:result['evaluation'][k] for k in ['tp','fp','fn','precision','recall','f1','reward','inspection_steps']}
        public=episode['public']
        findings=result['submission']['findings']
        comparisons={str(m['finding_index']):comparison(public,findings[m['finding_index']])
                     for m in result['evaluation']['matches']}
        cases.append(dict(id=slug,title=title,description=description,icon=symbol,
                          company='Компания «Орион»' if fixture else 'Синтетическая компания',public=public,
                          comparisons=comparisons,
                          trajectory=result['trajectories'],submission=result['submission'],evaluation=metrics,
                          steps=result['steps'],elapsed_seconds=result['elapsed_seconds']))
    report=json.loads((ROOT/'verification/report.json').read_text())
    payload=dict(version='1.0.0',mode='recorded_public_demonstration',cases=cases,
                 verification={k:report[k] for k in ['started_at','versions','unit_tests','acceptance','benchmark','paired_passed','sweep_passed','selected_mutants','mutants_killed','resource_bounds','boundary_run']})
    write_json(ROOT/'web/data/demo.json',payload)
    write_json(ROOT/'web/data/verification.json',report)
    matrix=json.loads((ROOT/'planning/acceptance-matrix.json').read_text())
    definitions={case['id']:{key:case[key] for key in ('title','procedure','expected')}
                 for group in matrix['groups'] for case in group['cases']}
    write_json(ROOT/'web/data/checks.json',definitions)
    html=(ROOT/'verification/report.html').read_text()
    match=re.search(r'<style>(.*?)</style>',html,re.S)
    if not match:raise ValueError('Report stylesheet not found')
    (ROOT/'web/assets/verification.css').write_text(match.group(1)+'\n')
    (ROOT/'web/assets/verification.html').write_text(html[:match.start()]+'<link rel="stylesheet" href="verification.css">'+html[match.end():])
    for name in ['demo.mp4','presentation.pdf','presentation.pptx']:
        shutil.copy2(ROOT/'demo'/name,ROOT/'web/assets'/name)
    print(f'Exported {len(cases)} public episodes and release assets; no truth/provenance/seed files included.')
if __name__=='__main__':main()
