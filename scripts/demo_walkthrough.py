"""Readable terminal demo of an actual CLI execution, followed by its saved trace."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser()
p.add_argument('case', choices=['fx', 'clean'])
p.add_argument('--start-file', type=Path, required=True)
p.add_argument('--done-file', type=Path, required=True)
a = p.parse_args()
fixture = 'manual_fx_period.json' if a.case == 'fx' else 'manual_clean.json'
output = ROOT / 'artifacts/live-demo/runs' / a.case
command = [sys.executable, '-m', 'sled', 'demo', '--fixture', 'fixtures/' + fixture,
           '--policy', 'reconciler', '--output', str(output.relative_to(ROOT))]
green = '\033[38;2;169;239;190m'
muted = '\033[38;2;145;171;155m'
white = '\033[38;2;230;242;233m'
reset = '\033[0m'
print('\033[2J\033[H' + green + 'evidable.  /  ЛОКАЛЬНЫЙ ЗАПУСК' + reset)
print(muted + 'Python 3.11 · скриптовая политика reconciler · агент в Docker без сети' + reset)
print()
while not a.start_file.exists():
    time.sleep(.05)
line = 'PYTHONPATH=src python3 -m sled demo --fixture fixtures/' + fixture
print(green + '$ ', end='', flush=True)
for char in line:
    print(char, end='', flush=True)
    time.sleep(.015)
print(" \\\n    --policy reconciler --output artifacts/live-demo/runs/" + a.case + reset)
print(muted + 'Выполняется реальная команда; полный JSON сохраняется рядом с видео.' + reset, flush=True)
env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'))
run = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
output.mkdir(parents=True, exist_ok=True)
(output / 'cli.stdout.json').write_text(run.stdout)
(output / 'cli.stderr.txt').write_text(run.stderr)
if run.returncode:
    print(run.stderr, flush=True)
    a.done_file.write_text(json.dumps(dict(exit_code=run.returncode)))
    raise SystemExit(run.returncode)
summary = json.loads(run.stdout)
result = json.loads((output / 'private/report.json').read_text())
trace = [json.loads(line) for line in (output / 'trajectories.jsonl').read_text().splitlines()]
assert summary['terminated'] and not summary['truncated']
print(green + '\nПРОГОН ЗАВЕРШЁН' + reset + '  ·  exit code 0')
print(muted + 'Сохранённая траектория этого запуска:' + reset)
for row in trace:
    action = row['action']
    detail = action.get('table', action.get('doc_id', ''))
    print(white + f'  {row["step"]:02}  {action["action"]:<16} {detail}' + reset, flush=True)
    time.sleep(.12)
e = result['evaluation']
print(green + f'\nTP {e["tp"]}   FP {e["fp"]}   FN {e["fn"]}   F1 {e["f1"]:.2f}   Награда {e["reward"]:.3f}' + reset)
print(white + f'{result["steps"]} действий · {result["elapsed_seconds"]:.3f} с · эпизод завершён' + reset)
labels = {'fx_conversion': 'Валютное расхождение', 'period_cutoff': 'Ошибка отчётного периода'}
findings = result['submission']['findings']
for f in findings:
    amount = f'{f["claimed_amount_minor"] / 100:,.0f}'.replace(',', ' ')
    print(white + f'\n{labels[f["type"]]}: {amount} {f["currency"]}' + reset)
    print(muted + '  Доказательства: ' + ', '.join(f['evidence_ids']) + reset)
if not findings:
    print(green + '\nНарушений нет. Частичная оплата оставляет законную задолженность.' + reset)
else:
    print(muted + '\nСуммы двух нарушений не складываются в общий ущерб.' + reset)
print(muted + '\nОценка раскрыта после завершения. Во время поиска эталон закрыт.' + reset, flush=True)
a.done_file.write_text(json.dumps(dict(exit_code=0,summary=summary), ensure_ascii=False))
while True:
    time.sleep(1)
