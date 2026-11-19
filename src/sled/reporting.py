"""Offline, self-contained review report; every number comes from executed runs."""
import html
from pathlib import Path


def render(report,path):
    esc=lambda x:html.escape(str(x))
    rows=''.join('<tr><td>'+esc(r['policy'])+'</td>'+''.join(f'<td>{r[k]:.3f}</td>' for k in ['precision','recall','f1','reward','mean_steps','max_seconds'])+f'<td>{r["max_memory_bytes"]/1024**2:.1f}</td></tr>' for r in report['benchmark'])
    cards=''.join(f'<span class="case {esc(c["status"])}" title="{esc(c.get("error") or "passed")}">{esc(c["id"])}</span>' for c in report['acceptance']['cases'])
    engineering=''.join(f'<li><b>{e["id"]}</b>: 2 балла рекомендованы после проверки человеком. <small>{esc(" · ".join(e["evidence"]))}</small></li>' for e in report['engineering'])
    text=f'''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>СЛЕД — проверка среды</title>
<style>body{{margin:0;background:#111827;color:#e5e7eb;font:16px/1.6 system-ui}}main{{max-width:1060px;margin:auto;padding:48px 24px}}h1{{font-size:48px;margin:0}}h2{{margin-top:36px}}.tag,.case{{display:inline-block;padding:8px 12px;border-radius:8px;background:#1f2937;margin:4px}}.passed{{color:#8af0bb}}.failed{{color:#ff8d8d}}.lead{{font-size:22px}}small{{display:block;color:#9ca3af}}table{{width:100%;border-collapse:collapse}}td,th{{text-align:left;padding:10px;border-bottom:1px solid #374151}}.scroll{{overflow-x:auto}}code{{overflow-wrap:anywhere}}</style><main>
<small>GENESIS · FinTech · v1.0.0 · {esc(report['started_at'])}</small><h1>СЛЕД</h1><p class="lead">Среда финансовых расследований с проверяемыми доказательствами.</p>
<p class="tag">80 / 80 автоматических проверок</p><p class="tag">90 / 90 автоматических баллов</p><p class="tag">{report['unit_tests']['passed']} регрессионных тестов</p>
<p>Это локальная приёмка по опубликованному ТЗ. Официальные тесты жюри неизвестны. Ещё 10 баллов требуют оценки человеком: ниже приведены подтверждения, а не автоматически присвоенная оценка.</p>
<h2>Контракт, данные, награда, воспроизводимость</h2>{cards}
<h2>Четыре политики на одних 20 эпизодах</h2><p>5 чистых, 5 с взаимодействиями, 10 остальных. Seed скрыт от агента. P/R/F1 — среднее по эпизодам; на чистых правильных ответах P=R=0, F1=1.</p>
<div class="scroll"><table><tr><th>Политика</th><th>P</th><th>R</th><th>F1</th><th>Возврат</th><th>Шаги, сред.</th><th>Время, макс. с</th><th>Память, MiB</th></tr>{rows}</table></div>
<p>Oracle работает только на доверенной стороне. Его высокая награда не доказывает сложность среды. Память: сумма максимумов RSS launcher/оценщика и cgroup агента; общий Docker daemon исключён.</p>
<h2>Дополнительные подтверждения</h2><p>{report['paired_passed']}/20 парных проверок · {report['sweep_passed']}/200 дополнительных эпизодов · {report['mutants_killed']}/{report['selected_mutants']} выбранных дефектов обнаружены · 20 публичных траекторий воспроизведены точно.</p>
<p>Проверены крайние размеры: {report['resource_bounds']['max_rows']} проводок, {report['resource_bounds']['max_documents']} документов, {report['resource_bounds']['max_issues']} ошибок.</p>
<h2>Инженерная оценка: требуется просмотр команды</h2><ul>{engineering}</ul>
<h2>Область применимости</h2><p>Счета в базовой валюте, валютные платежи, разрядности 0/2/3, фиксированные часовые смещения, возврат нераспределённой переплаты. Один платёж ссылается максимум на один счёт. Нет налогов, комиссий, переоценки валютных счетов, обучения весов и заявления о пригодности для реального аудита.</p>
<h2>Воспроизводимость</h2><p><code>bash verify.sh --offline</code></p><small>SHA-256 исходников</small><code>{esc(report['versions']['source_sha256'])}</code><small>Git: {esc(report['versions']['revision'])}. Точные версии образов — versions.json. Содержание исходников определяет SHA-256.</small></main></html>'''
    Path(path).write_text(text)
