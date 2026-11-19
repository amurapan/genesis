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

def main():
    definitions=[
        ('fx-period','Валюта и граница периода','Валютный платёж отражён по прежнему курсу и попал в следующий месяц.','manual_fx_period.json'),
        ('duplicates','Дубль и распределение','Счёт признан дважды, а часть полученного платежа осталась нераспределённой.','manual_errors.json'),
        ('clean','Чистая компания','Частично оплаченный счёт: задолженность есть, нарушений нет.','manual_clean.json'),
        ('generated','Сгенерированная компания','Все четыре типа ошибок, разбитые оплаты и корректные отвлекающие случаи.',None),
    ]
    cases=[]
    for slug,title,description,fixture in definitions:
        episode=json.loads((ROOT/'fixtures'/fixture).read_text()) if fixture else generate(20261119)
        verify_episode(episode)
        result=run_episode(episode,'reconciler','evaluation')
        assert not result['truncated'] and result['evaluation']['f1']==1
        metrics={k:result['evaluation'][k] for k in ['tp','fp','fn','precision','recall','f1','reward','inspection_steps']}
        cases.append(dict(id=slug,title=title,description=description,public=episode['public'],
                          trajectory=result['trajectories'],submission=result['submission'],evaluation=metrics,
                          steps=result['steps'],elapsed_seconds=result['elapsed_seconds']))
    report=json.loads((ROOT/'verification/report.json').read_text())
    payload=dict(version='1.0.0',mode='recorded_public_demonstration',cases=cases,
                 verification={k:report[k] for k in ['started_at','versions','unit_tests','acceptance','benchmark','paired_passed','sweep_passed','selected_mutants','mutants_killed','resource_bounds','boundary_run']})
    write_json(ROOT/'web/data/demo.json',payload)
    write_json(ROOT/'web/data/verification.json',report)
    html=(ROOT/'verification/report.html').read_text()
    match=re.search(r'<style>(.*?)</style>',html,re.S)
    if not match:raise ValueError('Report stylesheet not found')
    (ROOT/'web/assets/verification.css').write_text(match.group(1)+'\n')
    (ROOT/'web/assets/verification.html').write_text(html[:match.start()]+'<link rel="stylesheet" href="verification.css">'+html[match.end():])
    for name in ['demo.mp4','presentation.pdf']:
        shutil.copy2(ROOT/'demo'/name,ROOT/'web/assets'/name)
    print('Exported four public episodes and release assets; no truth/provenance/seed files included.')
if __name__=='__main__':main()
