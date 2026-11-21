"""Assemble real screen recordings. Run after scripts/record_demo.mjs.

Uses Python's standard library and FFmpeg. No voice is synthesized.
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'artifacts/live-demo'
DEST = ROOT / 'demo'
sys.path.insert(0, str(ROOT / 'src'))
from sled.metadata import source_fingerprint

segments = json.loads((RAW / 'segments.json').read_text())
recording = json.loads((RAW / 'recording.json').read_text())
report = json.loads((ROOT / 'verification/report.json').read_text())
assert report['versions']['source_sha256'] == source_fingerprint()
assert recording['public_submissions_match_actual_runs']
assert len(segments) == 7
script = {
    '01-intro': ('Что такое evidable', 'Это evidable — среда для проверки финансовых ИИ-агентов. Мы создаём вымышленные документы с известными ошибками и оцениваем выводы по доказательствам.'),
    'fx-cli': ('Настоящий запуск среды', 'Запускаем скриптового агента на заранее рассчитанном примере. Он работает в Docker без сети и не видит правильный ответ. После завершения показаны его действия и оценка: шесть шагов, два верных вывода, ни одного ложного обвинения. F1 равен единице. Полный результат и траектория сохранены в файлы.'),
    '03-laboratory': ('Документы и действия агента', 'В лаборатории показана сохранённая запись этого же примера. Здесь можно открыть первичный счёт и платёж: сто долларов поступили тридцатого ноября. Запускаем воспроизведение. Видно, какие данные агент запросил и как пришёл к выводам. После шестого действия появляются два нарушения: неверный валютный курс и ошибка отчётного периода.'),
    '04-evidence': ('Проверка доказательств', 'Откроем проводку. В книге записано сорок четыре тысячи тенге и первое декабря. Теперь проверим курс: четыреста пятьдесят тенге за доллар. Сто долларов должны дать сорок пять тысяч тенге, поэтому валютное расхождение — одна тысяча. Отдельно проверяется период платежа. Суммы этих двух нарушений не складываются в общий ущерб.'),
    'clean-cli': ('Чистая компания', 'Теперь настоящий запуск на чистой компании. Счёт оплачен частично, поэтому осталась законная задолженность. Агент не заявляет нарушений: список выводов пуст, F1 равен единице. Этот пример проверяет, что среда отличает ошибку от корректной операции.'),
    '06-verification': ('Проверки и изоляция', 'Сама среда прошла сорок восемь тестов и восемьдесят проверок нашей локальной матрицы. Это результаты команды, а не официальная оценка жюри. Генератор, агент и оценщик разделены; закрытый эталон остаётся на доверенной стороне.'),
    '07-reproduce': ('Как повторить', 'Исходники, учебные эпизоды и траектории приложены. Полная проверка запускается одной командой: bash verify.sh. Команда El Big 4, проект evidable.')
}
concat = RAW / 'concat.txt'
concat.write_text(''.join("file '" + str(Path(s['file'])).replace("'", "'\\''") + "'\n" for s in segments))
subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-f', 'concat', '-safe', '0',
                '-i', str(concat), '-c', 'copy', '-movflags', '+faststart',
                '-metadata', 'title=evidable — запуск среды и лаборатория', str(DEST / 'demo.mp4')], check=True)
probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_format', '-show_streams',
                                           '-of', 'json', str(DEST / 'demo.mp4')], text=True))
video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
assert video['width'] == 1920 and video['height'] == 1080
assert video['r_frame_rate'] == '25/1'
assert not any(s['codec_type'] == 'audio' for s in probe['streams'])
seconds = float(probe['format']['duration'])
assert abs(seconds - sum(s['seconds'] for s in segments)) < .15

def clock(t, ms=False):
    millis = round(t * 1000)
    h, rem = divmod(millis, 3600000)
    m, rem = divmod(rem, 60000)
    s, frac = divmod(rem, 1000)
    return f'{h:02}:{m:02}:{s:02},{frac:03}' if ms else f'{m:02}:{s:02}'

voice = ['# Текст для твоей озвучки', '',
         'Видео записано без звука. Добавь голос поверх `demo.mp4`; длину пауз можно подстроить под свою речь.',
         'Таймкоды совпадают с готовым MP4. `captions.srt` — необязательные субтитры для монтажа.', '']
subtitles = []
start = 0.0
chapters = []
for segment in segments:
    title, narration = script[segment['id']]
    end = start + segment['seconds']
    chapters.append(dict(id=segment['id'],title=title,start_seconds=round(start,3),end_seconds=round(end,3)))
    voice += [f'## {clock(start)}–{clock(end)} · {title}', '', narration, '']
    lines = textwrap.wrap(narration, width=50)
    chunks = ['\n'.join(lines[i:i+2]) for i in range(0, len(lines), 2)]
    weights = [len(c) for c in chunks]
    position = start
    for chunk, weight in zip(chunks, weights):
        finish = position + segment['seconds'] * weight / sum(weights)
        subtitles += [str(len(subtitles)//4+1), f'{clock(position,True)} --> {clock(finish,True)}', chunk, '']
        position = finish
    start = end
(DEST / 'narration.md').write_text('\n'.join(voice))
(DEST / 'captions.srt').write_text('\n'.join(subtitles))
for case, dest in [('fx','fx-period'), ('clean','clean')]:
    target = DEST / dest
    for name in ['private/report.json','trajectories.jsonl','cli.stdout.json']:
        p = target / name
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(RAW / 'runs' / case / name, p)
files = {str(p.relative_to(DEST)):hashlib.sha256(p.read_bytes()).hexdigest()
         for p in [DEST/'demo.mp4',DEST/'narration.md',DEST/'captions.srt']}
info = dict(kind='actual screen recording',seconds=seconds,width=1920,height=1080,fps=25,audio=False,
            narration='Human narration to be added by the team; Russian script and optional SRT supplied.',
            ffmpeg=subprocess.check_output(['ffmpeg','-version'],text=True).splitlines()[0],mss='10.1.0',
            source_sha256=source_fingerprint(),chapters=chapters,files=files,
            actual_runs={case:json.loads((RAW/'runs'/case/'cli.stdout.json').read_text()) for case in ['fx','clean']},
            browser_recording='Actual local application. The laboratory replays saved public trajectories; CLI cases were freshly executed during capture.',
            limitations='The recorder controls the UI and terminal. Quiet intervals between scenes are cut. No voice or music has been added.')
(DEST / 'media-tools.json').write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n')
shutil.copy2(DEST/'demo.mp4',ROOT/'web/assets/demo.mp4')
shutil.copy2(DEST/'narration.md',ROOT/'web/assets/narration.txt')
shutil.copy2(DEST/'captions.srt',ROOT/'web/assets/captions.srt')
release = ROOT/'artifacts/demo-release'
release.mkdir(exist_ok=True)
for name in ['demo.mp4','narration.md','captions.srt','media-tools.json']:
    (release/name).unlink(missing_ok=True)
    shutil.copy2(DEST/name,release/name)
for case in ['fx-period','clean']:
    shutil.copytree(DEST/case,release/case,dirs_exist_ok=True)
(release/'video-slides.pdf').unlink(missing_ok=True)
print(json.dumps(dict(seconds=seconds,bytes=(DEST/'demo.mp4').stat().st_size,chapters=chapters),ensure_ascii=False,indent=2))
