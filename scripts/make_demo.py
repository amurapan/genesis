"""Optional release media. Run with PyMuPDF 1.26.6; no model or network required."""
import json
from pathlib import Path
import subprocess
import fitz

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'artifacts/demo-release';DEST.mkdir(parents=True,exist_ok=True)
frames=DEST/'frames';frames.mkdir(exist_ok=True)
report=json.loads((ROOT/'artifacts/release/report.json').read_text())
demo=json.loads((DEST/'fx-period/private/report.json').read_text())
trace=[json.loads(x) for x in (DEST/'fx-period/trajectories.jsonl').read_text().splitlines()]
clean=json.loads((DEST/'clean/private/report.json').read_text())
rows={r['policy']:r for r in report['benchmark']}
real_actions=[x['action']['action']+(' '+x['action']['table'] if 'table' in x['action'] else '') for x in trace]
boundary=report['boundary_run']
slides=[
 ('SLED / GENESIS FinTech','A reproducible environment for financial investigations',[
  'Synthetic company -> public tools -> structured findings -> separate evaluator',
  'Four configurable fault types. Two interacting scenarios. Clean distractors.',
  'The environment is the product. Training model weights is optional.']),
 ('One manually calculated day','Foreign payment at the reporting boundary',[
  'Invoice: 100,000 KZT. Source payment: 100 USD on November 30.',
  'Published rate: 450 KZT / USD. Correct receipt: 45,000 KZT.',
  'Ledger: 44,000 KZT using the prior rate, posted on December 1.',
  'Reporting period ends on December 1 (exclusive).']),
 ('The investigation','Actual recorded tool calls from the isolated policy',[
  ' -> '.join(real_actions[:4]),' -> '.join(real_actions[4:]),
  f'{demo["steps"]} steps, {demo["elapsed_seconds"]:.3f} seconds. No shell, mounts, network or private seed.',
  'Full replayable interaction: demo/fx-period/trajectories.jsonl']),
 ('Two supported findings','Reference results revealed only after termination',[
  'FX conversion discrepancy: 100,000 minor KZT = 1,000 KZT.',
  'Period cutoff amount: 4,500,000 minor KZT = 45,000 KZT.',
  'Proof: payment document + cash journal + published FX row + policy / period.',
  f'TP={demo["evaluation"]["tp"]}, FP={demo["evaluation"]["fp"]}, F1={demo["evaluation"]["f1"]:.3f}. Closed agent reward stays zero.',
  'Amounts describe different faults; they are not added as total damages.']),
 ('Clean cases stay clean','A partial payment is not automatically a violation',[
  'Invoice: 1,000 KZT. Receipt: 600 KZT. Legitimate outstanding: 400 KZT.',
  f'Actual clean run: {len(clean["submission"]["findings"])} findings; F1={clean["evaluation"]["f1"]:.3f}.',
  'Split payments, refunds of excess cash, repeated amounts and null links are included.',
  'Evidence and exact amounts determine rewards; persuasive text does not.']),
 ('Four policies, same 20 episodes','5 clean + 5 interacting + 10 other scenarios',[
  f'{p:12} | mean F1 {rows[p]["f1"]:.3f} | mean return {rows[p]["reward"]:.3f} | mean steps {rows[p]["mean_steps"]:.1f}' for p in ['random','reconciler','flag_all','oracle']]),
 ('Executed release checks','Local evidence, not an official jury score',[
  f'{report["unit_tests"]["passed"]} regression tests; 80 / 80 acceptance cases = 90 / 90 automatic points.',
  f'{report["paired_passed"]} paired episodes; {report["sweep_passed"]} extra episodes; {report["mutants_killed"]} / {report["selected_mutants"]} selected defects caught.',
  '10 train + 10 dev; all 20 public trajectories replay exactly.',
  f'Boundary run: 2,000 ledger rows / 200 documents / 12 faults; {boundary["steps"]} steps, {boundary["elapsed_seconds"]:.3f}s.',
  'Five engineering criteria (10 points) are prepared for human review.']),
 ('Reproduce and review','bash run-offline.sh',[
  'The archive includes source, data, pinned images, reports and this demonstration.',
  'Limits: base-denominated invoices; one invoice per payment; surplus refunds only.',
  'No real audit certification, GPU dependency or claim of learned-model improvement.',
  'github.com/amurapan/genesis'])
]
pdf=fitz.open()
for index,(title,subtitle,lines) in enumerate(slides):
    page=pdf.new_page(width=1280,height=720)
    page.draw_rect(page.rect,color=None,fill=(.045,.065,.10))
    page.draw_rect(fitz.Rect(55,54,115,62),color=None,fill=(.49,.94,.71))
    page.insert_text((55,105),'SLED  /  REPRODUCIBLE AUDIT ENVIRONMENT',fontsize=14,color=(.55,.65,.74))
    page.insert_text((55,186),title,fontsize=42,color=(.96,.98,1),fontname='hebo')
    page.insert_textbox(fitz.Rect(55,215,1220,290),subtitle,fontsize=23,color=(.49,.94,.71))
    y=315
    for line in lines:
        size=20 if len(line)<112 else 18
        used=page.insert_textbox(fitz.Rect(55,y,1220,y+62),line,fontsize=size,color=(.84,.88,.93))
        if used<0:raise ValueError('Slide overflow: '+line)
        y+=63
    page.insert_text((55,680),f'Actual local run | source {report["versions"]["source_sha256"][:16]} | {index+1:02}/{len(slides):02}',fontsize=13,color=(.55,.65,.74))
    page.get_pixmap().save(frames/f'{index:02}.png')
pdf.save(DEST/'presentation.pdf')
image_id=subprocess.check_output(['docker','image','inspect','--format','{{.Id}}','linuxserver/ffmpeg:latest'],text=True).strip()
cmd=['docker','run','--rm','--network=none','-v',str(DEST)+':/work',image_id,
     '-y','-framerate','1/12','-i','/work/frames/%02d.png','-vf','fps=24,format=yuv420p',
     '-c:v','libx264','-preset','fast','-crf','22','-movflags','+faststart','/work/demo.mp4']
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
version=subprocess.check_output(['docker','run','--rm','--network=none',image_id,'-version'],text=True).splitlines()[0]
(DEST/'media-tools.json').write_text(json.dumps(dict(pymupdf=fitz.VersionBind,ffmpeg=version,image_id=image_id,
                seconds=len(slides)*12,slides=len(slides),source_sha256=report['versions']['source_sha256'],kind='explanatory slides from actual results'),indent=2)+'\n')
print(DEST/'demo.mp4')
