"""Create the Russian jury deck from the supplied Canva PDF design.

uv run --no-project --with pymupdf==1.26.6 --with python-pptx==1.0.2 \
  --with qrcode==8.2 --with pillow==12.0.0 python scripts/make_presentation.py

Use --template PATH once to refresh the text-free backgrounds. The source
slides, fonts and screenshots are retained under demo/presentation-assets.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

import fitz
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Pt
import qrcode

ROOT=Path(__file__).resolve().parents[1]
ASSETS=ROOT/'demo/presentation-assets'
W,H=1440,810
PURPLE='#B244A2';INK='#603A60';MUTED='#8A6187';PALE='#FDF2F2';WHITE='#FFFFFF'
SITE='https://sled-genesis.vercel.app'
CASE_URL=SITE+'/lab?episode=fx-period#workspace'
DEMO_URL=SITE+'/assets/demo.mp4'
TEAM_URL=SITE+'/team'
REPO_URL='https://github.com/amurapan/genesis'
PAGE_MAP=[0,1,2,3,9,0,5,7,8,5,1,10]
BG_PAGES=sorted(set(PAGE_MAP))
FONT_PATHS={False:ASSETS/'fonts/Montserrat-Regular.ttf',True:ASSETS/'fonts/Montserrat-Bold.ttf'}
FONTS={k:fitz.Font(fontfile=str(v)) for k,v in FONT_PATHS.items()}
SCALE=914400/90  # 1440 design units on a 16-inch wide slide.

def rgb(c):return tuple(int(c[i:i+2],16)/255 for i in (1,3,5))
def emu(x):return Emu(round(x*SCALE))
def prepare(template):
    source=fitz.open(template)
    for index in BG_PAGES:
        doc=fitz.open();doc.insert_pdf(source,from_page=index,to_page=index);p=doc[0]
        for block in p.get_text('blocks'):p.add_redact_annot(fitz.Rect(block[:4]),fill=None)
        p.apply_redactions(images=0,graphics=0,text=0)
        # Remove template branding; keep gradients, circles and layout containers.
        for rect in [(1200,55,1375,105),(1200,730,1380,780)]:p.add_redact_annot(fitz.Rect(rect),fill=None)
        if index==8:
            # The example's 77/54/24 percent charts do not describe our results.
            # Remove their paths and draw the verified full rings in the new deck.
            p.add_redact_annot(fitz.Rect(140,300,1280,530),fill=None)
        p.apply_redactions(images=0,graphics=1,text=0)
        assert not p.get_text().strip()
        p.get_pixmap(matrix=fitz.Matrix(4/3,4/3),alpha=False).save(ASSETS/f'background-{index+1:02}.png')
    (ASSETS/'template-source.json').write_text(json.dumps(dict(
        filename=Path(template).name,sha256=hashlib.sha256(Path(template).read_bytes()).hexdigest(),
        source_pages=len(source),used_pages=[i+1 for i in BG_PAGES],
        treatment='Original gradients and containers retained; template text, branding and example KPI charts removed.',
        typography='Montserrat Regular / Bold, Cyrillic; SIL Open Font License 1.1.'),ensure_ascii=False,indent=2)+'\n')


def lines_for(text,size,width,bold=False):
    result=[]
    for paragraph in text.split('\n'):
        words=paragraph.split(' ');line=''
        for word in words:
            candidate=(line+' '+word).strip()
            if FONTS[bold].text_length(candidate,fontsize=size)>width:
                if not line:raise ValueError(f'Word wider than text box: {word}')
                result.append(line);line=word
            else:line=candidate
        result.append(line)
    return result


class Deck:
    def __init__(self):
        self.pdf=fitz.open();self.pptx=Presentation();self.pptx.slide_width=emu(W);self.pptx.slide_height=emu(H)
        self.pptx.core_properties.title='evidable — среда финансовых расследований'
        self.pptx.core_properties.subject='GENESIS.EXE 2026 / FinTech'
        self.pptx.core_properties.author='El Big 4'
        self.layout=[]
    def slide(self,index,title,note):
        self.page=self.pdf.new_page(width=W,height=H)
        self.slide_obj=self.pptx.slides.add_slide(self.pptx.slide_layouts[6])
        self.number=len(self.pdf);self.items=[]
        bg=ASSETS/f'background-{index+1:02}.png'
        self.page.insert_image(self.page.rect,filename=str(bg))
        self.slide_obj.shapes.add_picture(str(bg),0,0,width=emu(W),height=emu(H))
        self.slide_obj.notes_slide.notes_text_frame.text=note
        self.slide_obj.name=title
        color=WHITE if index==7 else PURPLE
        self.text(1090,65,270,35,'evidable / EL BIG 4',18,bold=True,color=color,align='right')
        self.text(1250,764,110,25,f'{self.number:02} / 12',16,color=color,align='right')
        self.layout.append(dict(slide=self.number,title=title,template_page=index+1,elements=self.items))
    def text(self,x,y,w,h,text,size=26,bold=False,color=INK,align='left',leading=1.25,url=None):
        lines=lines_for(text,size,w,bold)
        needed=size*1.25+max(0,len(lines)-1)*size*leading
        if needed>h+.01:raise ValueError(f'Slide {self.number}, text overflow ({needed:.1f}>{h}): {text}')
        if x<0 or y<0 or x+w>W or y+h>H:raise ValueError('Text box outside page')
        fontname='MBold' if bold else 'MRegular'
        self.page.insert_font(fontname=fontname,fontfile=str(FONT_PATHS[bold]))
        for i,line in enumerate(lines):
            length=FONTS[bold].text_length(line,fontsize=size)
            tx=x+(w-length)/2 if align=='center' else x+w-length if align=='right' else x
            self.page.insert_text((tx,y+size*FONTS[bold].ascender+i*size*leading),line,
                                  fontname=fontname,fontsize=size,color=rgb(color))
        tb=self.slide_obj.shapes.add_textbox(emu(x),emu(y),emu(w),emu(h))
        tf=tb.text_frame;tf.clear();tf.margin_left=tf.margin_right=tf.margin_top=tf.margin_bottom=0
        tf.vertical_anchor=MSO_ANCHOR.TOP;tf.word_wrap=False
        for i,line in enumerate(lines):
            p=tf.paragraphs[0] if i==0 else tf.add_paragraph();p.text=line
            p.alignment={'left':PP_ALIGN.LEFT,'center':PP_ALIGN.CENTER,'right':PP_ALIGN.RIGHT}[align]
            p.space_before=Pt(0);p.space_after=Pt(0);p.line_spacing=Pt(size*.8*leading)
            for run in p.runs:
                run.font.name='Montserrat';run.font.size=Pt(size*.8);run.font.bold=bold
                run.font.color.rgb=RGBColor.from_string(color[1:])
                if url:run.hyperlink.address=url
        if url:self.page.insert_link({'kind':fitz.LINK_URI,'from':fitz.Rect(x,y,x+w,y+h),'uri':url})
        self.items.append(dict(kind='text',text=text,rect=[x,y,w,h],font_size=size,lines=len(lines)))
    def rect(self,x,y,w,h,fill=WHITE,stroke=None,stroke_width=1,rounded=False):
        r=fitz.Rect(x,y,x+w,y+h)
        self.page.draw_rect(r,color=rgb(stroke) if stroke else None,fill=rgb(fill) if fill else None,width=stroke_width)
        sh=self.slide_obj.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE if rounded else MSO_AUTO_SHAPE_TYPE.RECTANGLE,emu(x),emu(y),emu(w),emu(h))
        if fill:sh.fill.solid();sh.fill.fore_color.rgb=RGBColor.from_string(fill[1:])
        else:sh.fill.background()
        if stroke:sh.line.color.rgb=RGBColor.from_string(stroke[1:]);sh.line.width=Pt(stroke_width*.8)
        else:sh.line.fill.background()
        if rounded:sh.adjustments[0]=.06
    def ring(self,x,y,r,stroke=PURPLE,width=18):
        self.page.draw_circle((x,y),r,color=rgb(stroke),width=width)
        sh=self.slide_obj.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.OVAL,emu(x-r),emu(y-r),emu(2*r),emu(2*r))
        sh.fill.background();sh.line.color.rgb=RGBColor.from_string(stroke[1:]);sh.line.width=Pt(width*.8)
    def picture(self,path,x,y,w,h):
        pix=fitz.Pixmap(str(path));ratio=pix.width/pix.height
        actual_w=min(w,h*ratio);actual_h=actual_w/ratio
        x+=(w-actual_w)/2;y+=(h-actual_h)/2
        self.page.insert_image(fitz.Rect(x,y,x+actual_w,y+actual_h),filename=str(path))
        self.slide_obj.shapes.add_picture(str(path),emu(x),emu(y),width=emu(actual_w),height=emu(actual_h))
        self.items.append(dict(kind='image',source=str(path.relative_to(ROOT)),rect=[x,y,actual_w,actual_h]))
    def save(self):
        self.pdf.set_metadata(dict(title='evidable — среда финансовых расследований',author='El Big 4',
                                   subject='GENESIS.EXE 2026 / FinTech',keywords='evidable, FinTech, GENESIS, audit, RL environment'))
        self.pdf.subset_fonts()
        self.pdf.save(ROOT/'demo/presentation.pdf',garbage=4,deflate=True)
        self.pptx.save(ROOT/'demo/presentation.pptx')
        previews=ROOT/'artifacts/presentation-preview';previews.mkdir(parents=True,exist_ok=True)
        for i,page in enumerate(self.pdf):page.get_pixmap(matrix=fitz.Matrix(.8,.8)).save(previews/f'slide-{i+1:02}.png')
        (previews/'layout.json').write_text(json.dumps(self.layout,ensure_ascii=False,indent=2)+'\n')


def build():
    r=json.loads((ROOT/'verification/report.json').read_text());policies={x['policy']:x for x in r['benchmark']}
    d=Deck()
    d.slide(0,'evidable','Мы построили воспроизводимую среду финансовых расследований. Агент получает документы, исследует их через инструменты и отправляет выводы с доказательствами. Отдельный оценщик проверяет результат. Проект сделан командой El Big 4 для FinTech-кейса GENESIS.')
    d.text(150,180,1140,175,'evidable.',132,True,PURPLE,'center')
    d.text(180,374,1080,145,'У каждой ошибки\nесть след.',52,True,PURPLE,'center')
    d.text(170,562,1100,55,'Среда для финансового ИИ-аудитора',31,False,PURPLE,'center')
    d.text(140,699,600,40,'El Big 4 · GENESIS.EXE 2026',24,color=PURPLE)
    d.text(930,699,370,40,'Кейс FinTech',24,color=PURPLE,align='right')

    d.slide(1,'Проблема и аудитория','Разработчикам финансовых агентов нужны данные с известными ошибками и объективная проверка. Реальные книги закрыты, эталон трудно получить, а убедительный ответ может не содержать доказательств. Наша среда создаёт воспроизводимую задачу, не раскрывая агенту правильный ответ.')
    d.text(150,284,430,250,'Проверка агента\nначинается\nсо среды.',44,True,PURPLE,'center')
    d.text(690,120,640,130,'Выводы, которые\nможно проверить.',45,True,PURPLE)
    for y,h,b in [(285,'Данные','Вымышленная компания вместо\nзакрытых финансовых документов.'),(419,'Эталон','Причинно внесённые ошибки\nи доступные доказательства.'),(553,'Оценка','Структурированный ответ\nвместо оценки убедительности текста.')]:
        d.text(690,y,650,40,h,28,True,PURPLE);d.text(690,y+43,640,80,b,25)
    d.text(90,725,1240,45,'Для команд, которые разрабатывают финансовых агентов и RL-среды.',23,color=PURPLE)

    d.slide(2,'Четыре типа ошибок','Все четыре типа включаются независимо. Есть два взаимодействия: дубль с распределением и валютный платёж на границе периода. Чистые случаи включают частичные оплаты, разбитые платежи, возвраты переплаты и законные повторяющиеся суммы.')
    d.text(100,83,1240,80,'Четыре вида финансовых ошибок',51,True,PURPLE,'center')
    d.text(150,184,1140,55,'Независимые настройки. Взаимодействия. Чистые контрольные случаи.',25,color=PURPLE,align='center')
    cards=[('01','Дубли\nсчетов','Один счёт\nпризнан в книге\nповторно.'),('02','Распределение\nплатежа','Платёж получен,\nно применён\nне полностью.'),('03','Валютная\nконвертация','Неверный курс\nили дата его\nвыбора.'),('04','Отчётный\nпериод','Проводка попала\nв другой\nотчётный период.')]
    for x,(n,h,b) in zip([133,435,737,1039],cards):
        d.text(x+25,335,220,45,n,31,True,PURPLE)
        d.text(x+25,410,220,100,h,25,True,PURPLE)
        d.text(x+25,543,220,105,b,22)
    d.text(95,713,1240,55,'Законная задолженность и повторяющиеся суммы сами по себе не являются ошибками.',23,color=PURPLE,align='center')

    d.slide(3,'Архитектура и изоляция','Генератор сначала создаёт корректную историю, затем меняет конкретные записи. Среда предоставляет только публичные инструменты. Агент работает в отдельном контейнере без сети и mounts. Оценщик — отдельный процесс доверенной стороны, у которого остаются truth и provenance.')
    d.text(95,82,1250,80,'Эталон недоступен агенту',52,True,PURPLE,'center')
    blocks=[(100,216,'01 / Генератор','Согласованная история компании.\nОшибки с записанными изменениями.','seed + config'),(760,216,'02 / Среда','Документы через пять инструментов.\nБюджет, время и журнал действий.','reset / step'),(100,482,'03 / Агент в Docker','Без сети, mounts и доступа к truth.\nRead-only данные; до 100 действий.','reconciler / random / flag_all'),(760,482,'04 / Оценщик','Сопоставление с закрытым эталоном.\nTP, FP, FN, F1 и терминальная награда.','truth.json + provenance.json')]
    for x,y,h,b,c in blocks:
        d.text(x,y,575,60,h,33,True,PURPLE);d.text(x,y+75,565,100,b,25);d.text(x,y+185,565,35,c,21,color=PURPLE)

    d.slide(9,'Цикл расследования','Один эпизод — одна компания и один период. После reset агент видит задачу, manifest и политику. Затем использует инструменты чтения и калькулятор. submit завершает эпизод. Награда по ходу нулевая; при закрытой оценке итог остаётся у оценщика.')
    d.text(81,106,1260,135,'Одно расследование —\nдо 100 шагов',52,True,PURPLE)
    d.text(81,275,1220,90,'Документы → инструменты → выводы → оценка\nОдна компания. Один отчётный период. Воспроизводимый результат.',27,color=PURPLE)
    for x,h,b in [(81,'Компания','reset(seed, config)\nСчета, платежи,\nпроводки и policy.'),(393,'Исследование','Чтение записей\nи расчёты через\nограниченный API.'),(756,'Выводы','submit(findings)\nТип, сумма, IDs\nи доказательства.'),(1081,'Оценка','Matching с эталоном.\nМетрики, награда\nи траектория.')]:
        d.text(x,532,280,45,h,29,True,PURPLE);d.text(x,590,280,115,b,24)
    d.text(81,745,1140,30,'Страница — до 50 записей. Лимит 100 действий включает отправку ответа.',20,color=PURPLE)

    d.slide(0,'Лаборатория расследований','Откройте валютное дело. Слева находятся источники, справа — журнал и выводы. Пройдите шесть действий агента и откройте доказательство рядом с выводом. Браузер показывает запись реального прогона. Полная среда запускается локально.')
    d.text(80,102,1260,90,'Лаборатория расследований',54,True,PURPLE)
    d.rect(70,205,896,510,WHITE,'#EBCDE4',2)
    d.picture(ASSETS/'workbench.png',77,212,882,496)
    sections=[
        (229,'Выберите дело','Четыре открытых эпизода: валюта и период, дубль счёта, чистая книга и генерация.'),
        (409,'Пройдите шаги','В журнале видны запросы, ответы инструментов и остаток бюджета.'),
        (571,'Сверьте вывод','Откройте документ, проводку или курс рядом с результатом.'),
    ]
    for y,h,b in sections:
        d.text(1002,y,360,43,h,28,True,PURPLE);d.text(1002,y+47,350,115,b,22)
    d.text(80,741,1150,35,'Открыть дело «Валюта и граница периода»',20,color=PURPLE,url=CASE_URL)

    d.slide(5,'Ручной эпизод FX и периода','Платёж в 100 долларов поступил 30 ноября в 23:59:59 по UTC+5. За 30 ноября опубликован курс 450, поэтому получаем 45 тысяч тенге. Проводка на 44 тысячи соответствует курсу 440 за 29 ноября. В книге платёж записан в 00:00:00 1 декабря, уже в следующем периоде. Расхождение суммы — тысяча тенге. Объём события, отнесённого к другому периоду, — 45 тысяч тенге.')
    d.text(101,95,1240,90,'Один платёж. Две ошибки.',52,True,PURPLE)
    d.text(101,201,1230,70,'Платёж 100 USD · время в UTC+5\nTP = 2 · FP = 0 · FN = 0 · F1 = 1 · 6 шагов · награда 0,990',26,color=PURPLE)
    table(d,['Поле','По источнику','По проводке','Что обнаружено'],[
        ['Курс USD/KZT','450 · 30 ноября','440 · 29 ноября','Дата курса'],
        ['Поступление','45 000 KZT','44 000 KZT','Разница 1 000 KZT'],
        ['Время события','30.11 · 23:59:59','01.12 · 00:00:00','Граница периода'],
        ['Отчётный период','Ноябрь','Декабрь','45 000 KZT в декабре'],
    ])
    d.text(101,741,1200,55,'Сумма 44 000 KZT соответствует курсу за 29 ноября. Сумма ошибки периода — объём события.',20,color=INK)

    d.slide(7,'Доказательства и награда','Ответ засчитывается только при точном типе, затронутых ID, валюте и сумме в допуске, а также полном допустимом наборе доказательств. Matcher делает взаимно однозначное сопоставление. Повторный вывод становится FP. На чистой книге корректно не обвинять ни одну запись.')
    d.text(100,143,1240,150,'Ответ засчитывается только\nс полным доказательством.',50,True,WHITE,'center')
    d.text(110,318,1220,75,'Тип · сумма · валюта · затронутые IDs · доказательства',27,color=WHITE,align='center')
    d.text(70,418,1300,80,'clip(2 × F1 − 1 − 0.002 × шаги, −1, 1)',39,True,WHITE,'center')
    d.text(100,511,1240,35,'Шаги исследования; submit в стоимость не входит.',20,color=WHITE,align='center')
    for x,h,b in [(95,'Повторы → FP','Дубликат вывода\nне увеличивает награду.'),(530,'Чистый эпизод','Пустой правильный ответ\nполучает F1 = 1.'),(980,'Закрытая оценка','Награда и диагностика\nостаются у оценщика.')]:
        d.text(x,579,370,50,h,27,True,WHITE);d.text(x,642,370,85,b,24,color=WHITE)

    d.slide(8,'Проверка самой среды','Мы проверяем не только ответы политики, но и сам генератор, контракт и награду. Пройдены 48 регрессионных тестов без пропусков, 80 случаев локальной матрицы и 200 дополнительных эпизодов. Все 10 выбранных намеренных дефектов обнаружены. Это локальная приёмка, не официальная оценка жюри.')
    d.text(100,108,1240,90,'Проверена сама среда',55,True,PURPLE,'center')
    d.text(150,220,1140,60,'Данные, изоляция, награда и воспроизводимость.',27,color=PURPLE,align='center')
    for x,value,label in [(256,'48/48','Регрессионные\nтесты'),(709,'80/80','Проверки\nлокальной матрицы'),(1163,'200/200','Дополнительные\nэпизоды')]:
        d.ring(x,423,112,width=18);d.text(x-125,390,250,80,value,44,True,PURPLE,'center');d.text(x-185,572,370,88,label,28,True,PURPLE,'center')
    d.text(100,682,1240,40,'20 парных проверок · 10/10 выбранных дефектов обнаружены',23,color=PURPLE,align='center')
    d.text(95,736,1240,55,'90/90 за автоматическую часть локальной матрицы. 10 инженерных баллов — ручная оценка.',20,color=INK,align='center')

    d.slide(5,'Базовые политики','Все четыре политики проверяются на одинаковых 20 эпизодах: пяти чистых, пяти взаимодействующих и десяти остальных. Сверка решает поддерживаемый профиль, а массовые обвинения получают минус один. Oracle работает только у оценщика. Его единица — проверка потолка функции награды, не свидетельство сложности.')
    d.text(101,95,1240,90,'Четыре политики. Одна выборка.',48,True,PURPLE)
    d.text(101,204,1230,60,'20 общих эпизодов: 5 чистых, 5 с взаимодействиями, 10 остальных.',25,color=PURPLE)
    def n(x,digits):return f'{x:.{digits}f}'.replace('.',',')
    rows=[[k,n(policies[k]['f1'],3),n(policies[k]['reward'],3),n(policies[k]['mean_steps'],1)] for k in ['random','reconciler','flag_all','oracle']]
    table(d,['Политика','F1, среднее','Возврат, среднее','Шаги, среднее'],rows)
    d.text(101,741,1200,55,'Oracle знает эталон. Его результат проверяет потолок награды, а не сложность среды.',20,color=PURPLE)

    d.slide(1,'Воспроизводимость и ограничения','Для полного запуска нужны Linux, Python 3.11, Docker и cgroup v2. Одна команда выполняет обязательные проверки. После подготовки образов запуск автономен. Модель учёта намеренно ограничена: базовые счета, один счёт на платёж и возвраты переплаты; нет налогов, комиссий и обучения весов.')
    d.text(80,104,1240,85,'Запуск и границы продукта',50,True,PURPLE)
    d.text(140,276,460,75,'Одна команда',36,True,PURPLE,'center')
    d.text(120,380,500,70,'bash verify.sh',35,True,PURPLE,'center')
    d.text(140,485,460,110,'Linux · Python 3.11\nDocker · cgroup v2',25,color=PURPLE,align='center')
    d.text(700,250,630,65,'Поддержанный профиль',33,True,PURPLE)
    for y,b in [(346,'Счета в базовой валюте.\nВалютные поступления поддержаны.'),(459,'Один счёт на платёж.\nВозврат только переплаты.'),(572,'Без налогов, комиссий, переоценки\nвалютных счетов и обучения весов.')]:d.text(700,y,630,92,b,25)
    seconds=n(r['boundary_run']['elapsed_seconds'],3)
    d.text(90,723,1250,60,f'Предельный эпизод: 2 000 проводок, 200 документов, 12 ошибок — {r["boundary_run"]["steps"]} шагов и {seconds} с в локальном прогоне.',21,color=PURPLE)

    d.slide(10,'Повторите расследование','QR-код ведёт сразу к тому делу, которое мы разобрали в видео. Пройдите шесть действий и сами проверьте доказательства. В репозитории есть исходники, эпизоды и инструкции офлайн-запуска. Проект подготовила команда El Big 4.')
    d.text(92,108,1240,84,'Повторите расследование',56,True,PURPLE)
    d.text(92,199,1200,52,'Откройте дело → пройдите шесть шагов → сверьте доказательства',26,color=PURPLE)
    d.rect(92,270,820,216,WHITE,'#EBCDE4',2)
    links=[(292,'Дело «Валюта и граница периода»',CASE_URL),(353,'Смотреть демо · 2:42',DEMO_URL),
           (413,'Исходники на GitHub',REPO_URL)]
    for y,label,url in links:
        d.text(122,y,750,50,label,27,True,PURPLE,url=url)
    d.rect(1040,254,270,258,WHITE,'#EBCDE4',2)
    qr=qrcode.QRCode(version=None,error_correction=qrcode.constants.ERROR_CORRECT_M,box_size=12,border=4)
    qr.add_data(CASE_URL);qr.make(fit=True)
    qr.make_image(fill_color=PURPLE,back_color=WHITE).save(ASSETS/'demo-qr.png')
    d.picture(ASSETS/'demo-qr.png',1070,261,210,210)
    d.text(1050,468,250,37,'Открыть дело',21,True,PURPLE,'center',url=CASE_URL)
    d.text(92,556,500,52,'El Big 4',34,True,PURPLE)
    d.text(1050,567,260,37,'Страница команды',21,color=PURPLE,align='right',url=TEAM_URL)
    team=[('abylay','Абылай\nМуратов','Капитан'),('damir','Дамир\nАбдуалиев',''),
          ('adelina','Адэлина\nКурмангалиева',''),('alisultan','Alisultan\nTolegen','')]
    for x,(avatar,name,role) in zip([92,399,706,1013],team):
        d.rect(x,627,297,112,WHITE,'#EBCDE4',1)
        d.picture(ASSETS/'team'/f'{avatar}.jpg',x+13,642,83,83)
        d.text(x+110,644,180,58,name,20,True,INK,leading=1.2)
        if role:d.text(x+110,700,170,26,role,16,color=PURPLE)
    d.save()
    info=dict(title='evidable — среда финансовых расследований',language='ru',slides=12,
              template=json.loads((ASSETS/'template-source.json').read_text()),
              source_report='verification/report.json',verified_core_sha256=r['versions']['source_sha256'],
              tools={'PyMuPDF':'1.26.6','python-pptx':'1.0.2','qrcode':'8.2','Pillow':'12.0.0'},
              files={name:hashlib.sha256((ROOT/'demo'/name).read_bytes()).hexdigest() for name in ['presentation.pdf','presentation.pptx']},
              note='PDF has embedded Cyrillic fonts. PPTX text, diagrams and tables are editable; template backgrounds are retained as images. Speaker notes are included.')
    (ROOT/'demo/presentation-info.json').write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n')
    for folder in [ROOT/'web/assets',ROOT/'artifacts/demo-release']:
        if folder.is_dir():
            for name in ['presentation.pdf','presentation.pptx']:
                shutil.copy2(ROOT/'demo'/name,folder/name)
    print(json.dumps(dict(slides=len(d.pdf),pdf=str(ROOT/'demo/presentation.pdf'),pptx=str(ROOT/'demo/presentation.pptx')),ensure_ascii=False))


def table(d,headers,rows):
    xs=[101.4,419.9,738.4,1056.9];width=302.1
    for x,h in zip(xs,headers):d.text(x+10,313,width-20,45,h,22,True,WHITE,'center')
    for y,row in zip([396,483,570,657],rows):
        for j,(x,value) in enumerate(zip(xs,row)):d.text(x+10,y,width-20,52,value,25,j==0,PURPLE,'center')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--template',type=Path);args=parser.parse_args()
    ASSETS.mkdir(parents=True,exist_ok=True)
    if args.template:prepare(args.template)
    build()
