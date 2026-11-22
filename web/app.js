import { icon } from "./ui/icons.js";
const $ = (s) => document.querySelector(s);
const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const num = (n, d = 0) =>
  new Intl.NumberFormat("ru-RU", {
    minimumFractionDigits: d,
    maximumFractionDigits: d,
  }).format(n);
const date = (s) => String(s).slice(0, 10).split("-").reverse().join(".");
const short = (s) =>
  String(s).length > 22
    ? String(s).slice(0, 10) + "…" + String(s).slice(-5)
    : s;
const names = {
  duplicate_invoice: "Повторное признание счёта",
  payment_allocation: "Недораспределение платежа",
  fx_conversion: "Неверный валютный курс",
  period_cutoff: "Ошибка отчётного периода",
};
const comparisonLabels = {
  duplicate_invoice: "Повторный счёт",
  payment_allocation: "Распределение",
  fx_conversion: "Сумма и курс",
  period_cutoff: "Отчётный период",
};
const accounts = {
  accounts_receivable: "Дебиторская задолженность",
  revenue: "Выручка",
  cash: "Денежные средства",
  unapplied_cash: "Нераспределённый платёж",
};
const explanations = {
  duplicate_invoice:
    "Дебиторская задолженность признана на сумму больше первичного счёта. Повторные проводки подтверждают расхождение.",
  payment_allocation:
    "Часть уже полученного платежа не направлена на погашение счёта. Законная частичная оплата проверяется отдельно.",
  fx_conversion:
    "Сумма в книге отличается от первичного платежа, пересчитанного по опубликованной дате и курсу.",
  period_cutoff:
    "Дата первичного события и дата проводки относятся к разным отчётным периодам. Сумма — объём неверно отнесённого события.",
};
const groupNames = {
  C: "Контракт и изоляция",
  D: "Данные и эталон",
  R: "Надёжность награды",
  G: "Воспроизводимость",
};
let data,
  checkDefinitions = {},
  caseIndex = 0,
  step = 0,
  tab = "documents",
  docIndex = 0,
  page = 0,
  filter = "",
  selectedSource = "",
  raw = false,
  inspector = "results",
  findingIndex = 0,
  mobilePane = "sources",
  timer = null,
  toastTimer,
  checkGroup = "C",
  selectedCheck = "C01";
const savedCases = new Map();
const current = () => data.cases[caseIndex];
const finished = () => step === current().trajectory.length;
const comparisons = () => (finished() ? (current().comparisons ?? {}) : {});
const selectedComparison = () => comparisons()[findingIndex];
const route = () =>
  ["workspace", "verification", "architecture", "guide"].includes(
    location.hash.slice(1),
  )
    ? location.hash.slice(1)
    : "workspace";
const docs = () => [...current().public.invoices, ...current().public.payments];
const money = (minor, currency) => {
  const e = current().public.manifest.currency_exponents[currency];
  return num(minor / 10 ** e, e);
};
const json = (value) =>
  `<pre class='json-view'>${esc(JSON.stringify(value, null, 2))}</pre>`;
const status = (text) =>
  `<span class='status-pill'>${icon("check")}${esc(text)}</span>`;
function hydrate() {
  document
    .querySelectorAll("[data-icon]")
    .forEach((el) => (el.innerHTML = icon(el.dataset.icon)));
}
function stop() {
  clearInterval(timer);
  timer = null;
}
function toast(message) {
  $("#toast").textContent = message;
  $("#toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => ($("#toast").hidden = true), 2800);
}
function snapshot() {
  return {
    step,
    tab,
    docIndex,
    page,
    filter,
    selectedSource,
    raw,
    inspector,
    findingIndex,
    mobilePane,
  };
}
function selectCase(index, { reset = false } = {}) {
  stop();
  savedCases.set(current().id, snapshot());
  caseIndex = index;
  const s = reset ? {} : savedCases.get(current().id) || {};
  step = s.step || 0;
  tab = s.tab || "documents";
  docIndex = s.docIndex || 0;
  page = s.page || 0;
  filter = s.filter || "";
  selectedSource = s.selectedSource || "";
  raw = !!s.raw;
  inspector = s.inspector || "results";
  findingIndex = s.findingIndex || 0;
  mobilePane = s.mobilePane || "sources";
  const url = new URL(location.href);
  url.searchParams.set("episode", current().id);
  history.replaceState(null, "", url);
  render();
}
function render() {
  const active = document.activeElement;
  const focusId = active?.id;
  const focusKey = [
    "action",
    "tab",
    "step",
    "finding",
    "inspector",
    "group",
    "check",
    "case",
    "mobile",
  ].find((k) => active?.dataset?.[k] !== undefined);
  const focusValue = focusKey ? active.dataset[focusKey] : null;
  const scrolls = [...document.querySelectorAll("[data-scroll]")].map((el) => [
    el.dataset.scroll,
    el.scrollTop,
    el.scrollLeft,
  ]);
  const r = route();
  if (r !== "workspace") stop();
  document.body.dataset.route = r;
  document.querySelectorAll("[data-nav]").forEach((el) => {
    const on = el.dataset.nav === r;
    el.classList.toggle("active", on);
    el.setAttribute("aria-current", on ? "page" : "false");
  });
  $("#app").innerHTML = { workspace, verification, architecture, guide }[r]();
  hydrate();
  document.title =
    "evidable · " +
    {
      workspace: current().title,
      verification: "Проверки среды",
      architecture: "Устройство среды",
      guide: "Быстрый старт",
    }[r];
  for (const [key, y, x] of scrolls) {
    const el = document.querySelector(`[data-scroll='${key}']`);
    if (el) {
      el.scrollTop = y;
      el.scrollLeft = x;
    }
  }
  const target = focusId
    ? document.getElementById(focusId)
    : focusKey
      ? document.querySelector(`[data-${focusKey}='${CSS.escape(focusValue)}']`)
      : null;
  target?.focus({ preventScroll: true });
}
function sourceTabs() {
  return `<div class='source-tabs' role='tablist' aria-label='Источники дела'>${[
    ...(Object.keys(comparisons()).length
      ? [["comparison", "Сверка", null]]
      : []),
    ["documents", "Документы", current().public.manifest.document_count],
    ["ledger", "Проводки", current().public.ledger.length],
    ["policy", "Правила", null],
  ]
    .map(
      ([key, label, count]) =>
        `<button role='tab' tabindex='${tab === key ? 0 : -1}' aria-selected='${tab === key}' data-tab='${key}'>${label}${count === null ? "" : `<span>${count}</span>`}</button>`,
    )
    .join("")}</div>`;
}
function workspace() {
  const c = current(),
    m = c.public.manifest;
  return `<section class='case-header'><div><div class='case-breadcrumb'><span>Открытое расследование</span><span>/</span><code>${esc(c.id)}</code></div><h1>${esc(c.title)}</h1><p>${esc(c.company)}<span>·</span>${date(m.period_start)} — ${date(m.period_end)}<span>·</span>${esc(m.base_currency)}</p></div><div class='case-header-actions'><label class='case-select'><span class='sr-only'>Выбрать дело</span><select id='episode-select' aria-label='Выбрать эпизод'>${data.cases.map((x, i) => `<option value='${i}' ${i === caseIndex ? "selected" : ""}>${esc(x.title)}</option>`).join("")}</select>${icon("chevron")}</label><button class='tool-button' data-action='share' aria-label='Скопировать ссылку на дело'>${icon("copy")}</button><button class='tool-button' data-action='download-episode' aria-label='Скачать документы дела'>${icon("download")}</button></div></section>
 <div class='mobile-workspace-tabs' role='tablist' aria-label='Панели расследования'><button data-mobile='sources' role='tab' tabindex='${mobilePane === "sources" ? 0 : -1}' aria-selected='${mobilePane === "sources"}'>${icon("file")}Источники</button><button data-mobile='analysis' role='tab' tabindex='${mobilePane === "analysis" ? 0 : -1}' aria-selected='${mobilePane === "analysis"}'>${icon("eye")}Разбор${finished() ? `<span>${c.submission.findings.length}</span>` : ""}</button></div>
 <div class='investigation-desk' data-mobile-pane='${mobilePane}'><aside class='case-library'><div class='rail-label'>Библиотека дел <span>${data.cases.length}</span></div><div class='case-list'>${data.cases.map((x, i) => `<button class='case-item ${i === caseIndex ? "selected" : ""}' data-case='${i}' aria-pressed='${i === caseIndex}'><span class='case-symbol'>${icon(x.icon)}</span><span><strong>${esc(x.title)}</strong><small>${x.public.manifest.document_count} док. · ${x.steps} шагов</small></span>${(i === caseIndex ? step : savedCases.get(x.id)?.step) === x.trajectory.length ? `<span class='case-complete'>${icon("check")}</span>` : ""}</button>`).join("")}</div><div class='rail-note'><span class='rail-mark'>${icon("lock")}</span><strong>Вы исследуете<br>открытую запись.</strong><p>Все операции вымышлены. Здесь воспроизводится уже выполненный прогон агента.</p><a href='#guide'>Как пройти расследование</a></div><a class='rail-bottom' href='#verification'>${icon("shield")}Надёжность среды<span>${data.verification.acceptance.cases.filter((c) => c.status === "passed").length}/${data.verification.acceptance.cases.length}</span></a></aside>
 <section class='source-workspace' aria-label='Просмотр источника'><div class='source-toolbar'>${sourceTabs()}${tab === "comparison" ? "" : `<button class='tool-button raw-toggle ${raw ? "selected" : ""}' data-action='raw' aria-label='${raw ? "Показать читаемый вид" : "Показать исходный JSON"}' aria-pressed='${raw}'>${icon("code")}</button>`}</div><div class='source-content' data-scroll='sources' id='source-content'>${sourceContent()}</div><div class='source-footer'>${icon("shield")}${tab === "comparison" ? "Сверка по открытым источникам" : "Первичный источник"}<span>Только чтение</span></div></section>
 <aside class='analysis-workspace' aria-label='Разбор расследования'><div class='analysis-tabs' role='tablist' aria-label='Результат или журнал'><button data-inspector='results' role='tab' tabindex='${inspector === "results" ? 0 : -1}' aria-selected='${inspector === "results"}'>Выводы${finished() ? `<span>${c.submission.findings.length}</span>` : ""}</button><button data-inspector='trace' role='tab' tabindex='${inspector === "trace" ? 0 : -1}' aria-selected='${inspector === "trace"}'>Журнал <span>${step}/${c.trajectory.length}</span></button></div><div class='analysis-content' data-scroll='analysis' id='results'>${inspector === "results" ? findings() : trace()}</div></aside></div>${transport()}`;
}
function sourceContent() {
  if (tab === "comparison") return comparisonView();
  if (tab === "documents") {
    const all = docs();
    docIndex = Math.min(docIndex, all.length - 1);
    const d = all[docIndex];
    return `<div class='document-switcher'><label for='document-select'>Открытый документ</label><div><select id='document-select'>${all.map((x, i) => `<option value='${i}' ${i === docIndex ? "selected" : ""}>${x.invoice_id ? "Счёт" : "Платёж"} · ${short(x.invoice_id || x.payment_id)} · ${money(x.total_minor ?? x.amount_minor, x.currency)} ${x.currency}</option>`).join("")}</select>${icon("chevron")}</div></div>${selectedSource ? sourceContext(selectedSource) : ""}${raw ? json(d) : documentSheet(d)}`;
  }
  if (tab === "ledger") return ledgerView();
  return policyView();
}
function sourceContext(id) {
  return `<div class='source-context'>${icon("eye")}<span>Открыто доказательство <strong>${esc(proofName(id))}</strong></span><button data-action='clear-source' aria-label='Снять выделение доказательства'>${icon("close")}</button></div>`;
}
function comparisonCard(record, label) {
  return `<article class='comparison-card'><header><span>${esc(label)}</span><h3>${esc(record.title)}</h3></header>
    <dl>${record.fields
      .map((field) => {
        const value = field.currency
          ? money(field.minor, field.currency) + " " + field.currency
          : field.text;
        return `<div class='comparison-field${field.mismatch ? " comparison-mismatch" : ""}'><dt>${esc(field.label)}${field.mismatch ? "<span>Расхождение</span>" : ""}</dt><dd>${esc(value)}</dd></div>`;
      })
      .join("")}</dl>
    <footer>${record.sources.map((id) => `<button class='comparison-source' data-proof='${esc(id)}' title='${esc(id)}'>${icon(proofIcon(id))}${esc(proofName(id))}</button>`).join("")}</footer>
  </article>`;
}
function comparisonView() {
  const item = selectedComparison();
  if (!item)
    return `<p class='source-note'>Выберите подтверждённый вывод для сверки.</p>`;
  const findings = current().submission.findings;
  const finding = findings[findingIndex];
  const choices = Object.keys(comparisons());
  return `<section class='comparison-sheet' aria-labelledby='comparison-title'>
    <div class='comparison-heading'>${status("Подтверждено оценщиком")}<h2 id='comparison-title'>${esc(names[finding.type])}</h2><p>${esc(item.note)}</p></div>
    ${
      choices.length > 1
        ? `<label class='comparison-picker' for='comparison-finding'><span>Вывод для сверки</span><select id='comparison-finding'>${choices
            .map((index) => {
              const type = findings[index].type;
              const sameType = choices.filter(
                (key) => findings[key].type === type,
              );
              const suffix =
                sameType.length > 1 ? ` · ${sameType.indexOf(index) + 1}` : "";
              return `<option value='${index}' ${Number(index) === findingIndex ? "selected" : ""}>${esc(comparisonLabels[type] + suffix)}</option>`;
            })
            .join("")}</select>${icon("chevron")}</label>`
        : ""
    }
    <div class='comparison-pair'>${comparisonCard(item.reference, "Источник и правило")}${comparisonCard(item.booked, "Записано в учёте")}</div>
  </section>`;
}
function documentSheet(d) {
  const invoice = "invoice_id" in d;
  const amount = d.total_minor ?? d.amount_minor;
  const linked = invoice
    ? current().public.payments.filter((p) =>
        p.invoice_refs?.includes(d.invoice_id),
      )
    : current().public.invoices.filter((i) =>
        d.invoice_refs?.includes(i.invoice_id),
      );
  return `<article class='document-sheet'><div class='paper-letterhead'><span>evidable<span class='paper-slash'>/</span>ОТКРЫТЫЕ ДАННЫЕ</span><span>${invoice ? "INVOICE" : "PAYMENT"}</span></div><div class='paper-title'><div><span>${invoice ? "Первичный счёт" : "Платёжный документ"}</span><h2>${invoice ? "Счёт на оплату" : "Поступление средств"}</h2></div>${icon(invoice ? "receipt" : "bank")}</div><div class='paper-reference'>${esc(d.invoice_id || d.payment_id)}</div><div class='paper-facts'><div><span>${invoice ? "Дата выставления" : "Дата события"}</span><strong>${date(d.issued_at || d.timestamp)}</strong></div><div><span>${invoice ? "Срок оплаты" : "Валюта платежа"}</span><strong>${invoice ? date(d.due_at) : esc(d.currency)}</strong></div></div>
 ${invoice ? `<div class='paper-table-wrap'><table class='paper-table'><thead><tr><th>Наименование</th><th>Кол-во</th><th>Сумма, ${esc(d.currency)}</th></tr></thead><tbody>${d.line_items.map((l) => `<tr><td>${esc(l.description)}</td><td>${esc(l.quantity)}</td><td>${money(l.total_minor, d.currency)}</td></tr>`).join("")}</tbody></table></div>` : `<div class='payment-statement'>${icon("wallet")}<p>Сумма первичного платежа в валюте поступления. Конвертация определяется опубликованной политикой учёта.</p></div>`}
 <div class='paper-total'><span>${invoice ? "Итого к оплате" : "Получено"}</span><strong>${money(amount, d.currency)} <small>${esc(d.currency)}</small></strong></div><div class='paper-bottom'><span>Синтетический документ</span><span title='${esc(d.doc_id)}'>${esc(short(d.doc_id))}</span></div></article>
 ${linked.length ? `<div class='related-documents'><h3>Связанные ${invoice ? "платежи" : "счета"}</h3>${linked.map((x) => `<button data-proof='doc:${esc(x.doc_id)}'>${icon(invoice ? "wallet" : "receipt")}<span>${esc(short(x.payment_id || x.invoice_id))}</span><strong>${money(x.amount_minor ?? x.total_minor, x.currency)} ${esc(x.currency)}</strong></button>`).join("")}</div>` : `<p class='source-note'>У документа нет явных связанных ${invoice ? "платежей" : "счетов"} в этом эпизоде.</p>`}`;
}
function ledgerView() {
  const rows = current().public.ledger.filter((x) =>
    Object.values(x).join(" ").toLowerCase().includes(filter.toLowerCase()),
  );
  const selected = resolveProof(selectedSource);
  return `<div class='ledger-toolbar'><label class='search-field'>${icon("search")}<input id='ledger-search' type='search' value='${esc(filter)}' placeholder='ID, счёт или валюта' aria-label='Поиск проводок'></label><span>${rows.length} записей</span></div>${selectedSource ? sourceContext(selectedSource) : ""}${
    raw
      ? json(selected || rows)
      : `${selected ? recordSheet(selected) : ""}<div class='ledger-table-wrap'><table class='data-table'><thead><tr><th>Запись / счёт</th><th>Дата</th><th>Дебет</th><th>Кредит</th></tr></thead><tbody>${
          rows
            .slice(page * 8, page * 8 + 8)
            .map(
              (x) =>
                `<tr class='${selectedSource === "ledger:" + x.row_id ? "selected-row" : ""}'><td><button data-proof='ledger:${esc(x.row_id)}' title='${esc(x.row_id)}'>${esc(short(x.row_id))}</button><small>${esc(accounts[x.account] || x.account)}</small></td><td>${date(x.timestamp)}<small>${esc(x.currency)}</small></td><td class='amount'>${x.debit_minor ? money(x.debit_minor, x.currency) : "—"}</td><td class='amount'>${x.credit_minor ? money(x.credit_minor, x.currency) : "—"}</td></tr>`,
            )
            .join("") ||
          `<tr><td colspan='4' class='search-empty'>Совпадений нет. Попробуйте другой ID или валюту.</td></tr>`
        }</tbody></table></div>${pagination(rows.length, 8)}${selected ? "" : `<div class='table-hint'>${icon("eye")}Выберите запись, чтобы посмотреть реквизиты.</div>`}`
  }`;
}
function recordSheet(r) {
  return `<article class='record-sheet'><div class='record-title'>${icon("layers")}<h3>Проводка <span>${esc(short(r.row_id))}</span></h3></div><dl><div><dt>Бухгалтерский счёт</dt><dd>${esc(accounts[r.account] || r.account)}</dd></div><div><dt>Время записи</dt><dd>${esc(r.timestamp)}</dd></div><div><dt>Дебет</dt><dd>${money(r.debit_minor, r.currency)} ${esc(r.currency)}</dd></div><div><dt>Кредит</dt><dd>${money(r.credit_minor, r.currency)} ${esc(r.currency)}</dd></div><div><dt>Связанный счёт</dt><dd>${esc(r.invoice_id ?? "Нет явной связи")}</dd></div><div><dt>Связанный платёж</dt><dd>${esc(r.payment_id ?? "Нет явной связи")}</dd></div></dl><details><summary>Исходная запись JSON</summary>${json(r)}</details></article>`;
}
function policyView() {
  const p = current().public;
  const selected = resolveProof(selectedSource);
  return `${selectedSource ? sourceContext(selectedSource) : ""}${
    raw
      ? json(selected || p.policy)
      : `<article class='policy-sheet'><span class='section-kicker'>ПОЛИТИКА УЧЁТА</span><h2>Правила этой компании</h2><div class='rule-row'><span>Базовая валюта</span><strong>${esc(p.manifest.base_currency)}</strong></div><div class='rule-row'><span>Отчётный период</span><strong>${date(p.manifest.period_start)} — ${date(p.manifest.period_end)}</strong></div><p>Начало периода включено, конец исключён. Курс выбирается по дате исходного платёжного документа.</p><div class='rule-row'><span>Округление</span><code>${esc(p.policy.rounding)}</code></div><div class='rule-row'><span>Допуск суммы</span><strong>${p.policy.amount_tolerance_minor} мин. ед.</strong></div><div class='formula'>base_minor = round(payment_minor × rate<br>× 10^base_exponent / 10^payment_exponent)</div><details><summary>Полная политика JSON</summary>${json(p.policy)}</details><details ${selectedSource === "manifest:episode" ? "open" : ""}><summary>Manifest эпизода</summary>${json(p.manifest)}</details></article><section class='fx-register'><h3>Опубликованные курсы</h3>${
          p.fx.length
            ? `<div class='ledger-table-wrap'><table class='data-table'><thead><tr><th>Дата</th><th>Пара</th><th>Курс</th></tr></thead><tbody>${p.fx
                .slice(page * 8, page * 8 + 8)
                .map((x) => {
                  const id = `fx:${x.date}:${x.source_currency}:${x.target_currency}`;
                  return `<tr class='${selectedSource === id ? "selected-row" : ""}'><td>${date(x.date)}</td><td>${esc(x.source_currency)} / ${esc(x.target_currency)}</td><td><button data-proof='${esc(id)}'>${esc(x.rate)}</button></td></tr>`;
                })
                .join("")}</tbody></table></div>${pagination(p.fx.length, 8)}`
            : `<p class='source-note'>В этом эпизоде валютные курсы не требуются.</p>`
        }</section>`
  }`;
}
function pagination(total, size) {
  return `<div class='table-pagination'><span>${total ? page * size + 1 : 0}–${Math.min((page + 1) * size, total)} из ${total}</span><div><button class='tool-button' data-action='page-prev' aria-label='Предыдущая страница' ${page === 0 ? "disabled" : ""}>${icon("left")}</button><button class='tool-button' data-action='page-next' aria-label='Следующая страница' ${(page + 1) * size >= total ? "disabled" : ""}>${icon("right")}</button></div></div>`;
}
function findings() {
  const c = current();
  if (!finished())
    return `<div class='analysis-intro'><div class='orbit-symbol'>${icon("nodes")}<i></i><i></i></div><span class='section-kicker'>СОБЕРИТЕ КАРТИНУ</span><h2>От источника<br>к доказательству.</h2><p>Просмотрите документы или запустите запись. Агент покажет, какие данные он запросил и к чему пришёл.</p><div class='start-guide-mini'><div><span>${icon("file")}</span><p>Откройте первичные документы.</p></div><div><span>${icon("play")}</span><p>Пройдите ${c.steps} действий агента.</p></div><div><span>${icon("check")}</span><p>Сопоставьте вывод с источниками.</p></div></div><button class='text-button' data-action='finish'>Открыть готовый результат</button><p class='recorded-disclaimer'>Записанный прогон · ${c.id}<br>Новые вычисления в браузере не выполняются.</p></div>`;
  const m = c.evaluation;
  const summary = `<div class='result-strip'><span>Оценка завершена</span>${status("Проверено")}<div><strong>${num(m.f1, 2)}</strong><span>F1</span><strong>${num(m.reward, 3)}</strong><span>Возврат</span></div><details><summary>Все метрики</summary><dl class='metric-list'><div><dt>Precision / Recall</dt><dd>${num(m.precision, 2)} / ${num(m.recall, 2)}</dd></div><div><dt>TP / FP / FN</dt><dd>${m.tp} / ${m.fp} / ${m.fn}</dd></div><div><dt>Время прогона</dt><dd>${num(c.elapsed_seconds, 3)} с</dd></div></dl></details></div>`;
  if (!c.submission.findings.length)
    return `${summary}<div class='clean-conclusion'>${icon("shield")}<h2>Нарушений<br>не обнаружено.</h2><p>${esc(c.description)}</p><span>Чистый ответ: F1 = 1, P = R = 0.</span></div><button class='download-result' data-action='download-findings'>${icon("download")}Скачать выводы</button>`;
  findingIndex = Math.min(findingIndex, c.submission.findings.length - 1);
  const f = c.submission.findings[findingIndex];
  return `${summary}<div class='finding-list'>${c.submission.findings.map((x, i) => `<button class='finding ${i === findingIndex ? "selected" : ""}' data-finding='${i}' aria-pressed='${i === findingIndex}'><span class='finding-marker'>${icon("check")}</span><span><strong>${esc(names[x.type])}</strong><small>${money(x.claimed_amount_minor, x.currency)} ${esc(x.currency)}</small></span></button>`).join("")}</div><article class='finding-detail'><span class='section-kicker'>ВЫБРАННЫЙ ВЫВОД</span><h2>${esc(names[f.type])}</h2><div class='finding-value'>${money(f.claimed_amount_minor, f.currency)} <span>${esc(f.currency)}</span></div><p>${esc(explanations[f.type])}</p>${selectedComparison() ? `<button class='comparison-open' data-action='compare'>${icon("layers")}Сверить поля</button>` : ""}<div class='evidence-heading'><h3>Доказательства</h3><span>${f.evidence_ids.length} · источники</span></div><div class='evidence-list'>${f.evidence_ids.map((id) => `<button class='evidence-link ${selectedSource === id ? "selected" : ""}' data-proof='${esc(id)}'>${icon(proofIcon(id))}<span><strong>${esc(proofName(id))}</strong><small>${esc(short(id))}</small></span>${selectedSource === id ? icon("eye") : icon("file")}</button>`).join("")}</div><p class='evidence-hint'>Выберите источник — он откроется рядом.</p></article><button class='download-result' data-action='download-findings'>${icon("download")}Скачать выводы JSON</button><p class='analysis-footnote'>Суммы разных нарушений не складываются в общий ущерб. Здесь показана диагностика оценщика после завершения.</p>`;
}
function trace() {
  const c = current(),
    t = step ? c.trajectory[step - 1] : null;
  return `<div class='trace-heading'><span class='section-kicker'>ТРАЕКТОРИЯ АГЕНТА</span><h2>${step ? "Шаг " + step + " из " + c.steps : "Расследование ещё не начато"}</h2><p>reconciler · изолированный Docker</p></div><div class='trace-timeline'>${c.trajectory.map((x, i) => `<button class='trace-step ${step > i ? "done" : ""} ${step === i + 1 ? "current" : ""}' data-step='${i + 1}' aria-label='Шаг ${i + 1}: ${esc(x.action.action)}'><span>${step > i ? icon("check") : i + 1}</span><span><strong>${esc(actionTitle(x.action))}</strong><small>${esc(x.action.action)}${x.action.table ? " · " + esc(x.action.table) : ""}</small></span></button>`).join("")}</div>${t ? `<section class='step-observation'><h3>Ответ инструмента</h3><p>${stepSummary(t)}</p><div class='observation-meta'><span>Осталось ${t.observation.remaining_steps} шагов</span><span>Награда: ${num(t.reward)}</span></div><details open><summary>Запрос</summary>${json(t.action)}</details><details><summary>Полученное наблюдение</summary>${json(t.observation)}</details></section>` : `<p class='analysis-footnote'>Запустите воспроизведение или выберите любой шаг в журнале.</p>`}`;
}
function actionTitle(a) {
  if (a.action === "submit") return "Отправка выводов";
  if (a.action === "get_document") return "Чтение документа";
  if (a.action === "calculator") return "Проверка расчёта";
  return (
    {
      ledger: "Чтение проводок",
      invoices: "Чтение счетов",
      payments: "Чтение платежей",
      fx: "Проверка курсов",
    }[a.table] || "Запрос записи"
  );
}
function stepSummary(t) {
  if (t.action.action === "submit")
    return "Выводы переданы оценщику. Оценка закрытого прогона не возвращалась агенту.";
  const r = t.observation.result?.records;
  return r
    ? `Получено ${r.length} записей через разрешённый инструмент.`
    : "Получен ответ через ограниченный интерфейс среды.";
}
function transport() {
  return `<div class='transport-bar'><div class='transport-label'><span class='record-symbol'>${icon("play")}</span><div><strong>Запись расследования</strong><span>reconciler · ${current().steps} шагов</span></div></div><div class='transport-buttons'><button class='tool-button' data-action='reset' aria-label='В начало'>${icon("reset")}</button><button class='play-button' data-action='play' aria-label='${timer ? "Приостановить" : "Воспроизвести"}'>${icon(timer ? "pause" : "play")}<span>${timer ? "Пауза" : finished() ? "Повторить" : "Воспроизвести"}</span></button><button class='tool-button' data-action='next' aria-label='Следующий шаг' ${finished() ? "disabled" : ""}>${icon("next")}</button></div><div class='transport-scrubber'><label for='replay-range'>Шаг <strong id='scrub-value'>${step}</strong> / ${current().steps}</label><input id='replay-range' type='range' min='0' max='${current().steps}' value='${step}' aria-label='Перейти к шагу расследования'></div><div class='transport-budget'><strong>${100 - step}<span>/ 100</span></strong><small>осталось действий</small></div><button class='finish-button' data-action='finish'>${icon("check")}Итоги</button></div>`;
}
function proofIcon(id) {
  return id.startsWith("ledger:")
    ? "layers"
    : id.startsWith("fx:")
      ? "bank"
      : id.startsWith("policy:")
        ? "book"
        : "file";
}
function proofName(id) {
  if (id.startsWith("policy:")) return "Политика учёта";
  if (id.startsWith("manifest:")) return "Отчётный период";
  if (id.startsWith("fx:")) return "Курс " + id.split(":").slice(-2).join("/");
  if (id.startsWith("ledger:")) return "Проводка " + short(id.slice(7));
  return current().public.invoices.some((x) => "doc:" + x.doc_id === id)
    ? "Первичный счёт"
    : "Первичный платёж";
}
function resolveProof(id) {
  const p = current().public;
  if (id === "policy:accounting") return p.policy;
  if (id === "manifest:episode") return p.manifest;
  if (id.startsWith("ledger:"))
    return p.ledger.find((x) => "ledger:" + x.row_id === id);
  if (id.startsWith("doc:"))
    return docs().find((x) => "doc:" + x.doc_id === id);
  if (id.startsWith("fx:"))
    return p.fx.find(
      (x) => `fx:${x.date}:${x.source_currency}:${x.target_currency}` === id,
    );
}
function openSource(id) {
  if (!resolveProof(id)) return toast("Источник не найден");
  stop();
  selectedSource = id;
  raw = false;
  filter = "";
  page = 0;
  if (id.startsWith("doc:")) {
    tab = "documents";
    docIndex = docs().findIndex((x) => "doc:" + x.doc_id === id);
  } else if (id.startsWith("ledger:")) {
    tab = "ledger";
    page = Math.floor(
      current().public.ledger.findIndex((x) => "ledger:" + x.row_id === id) / 8,
    );
  } else {
    tab = "policy";
    if (id.startsWith("fx:"))
      page = Math.floor(
        current().public.fx.findIndex(
          (x) =>
            `fx:${x.date}:${x.source_currency}:${x.target_currency}` === id,
        ) / 8,
      );
  }
  mobilePane = "sources";
  render();
  $("#source-content").scrollTop = 0;
  showMobilePane();
}
function showMobilePane() {
  if (matchMedia("(max-width: 800px)").matches)
    document
      .querySelector(".mobile-workspace-tabs")
      ?.scrollIntoView({ block: "start", behavior: "instant" });
}
function setStep(value, { follow = true } = {}) {
  step = Math.max(0, Math.min(Number(value), current().trajectory.length));
  selectedSource = "";
  raw = false;
  if (finished()) {
    stop();
    inspector = "results";
    if (selectedComparison()) {
      tab = "comparison";
      mobilePane = "sources";
    } else {
      mobilePane = "analysis";
    }
  } else if (step) {
    inspector = "trace";
    if (follow) {
      const a = current().trajectory[step - 1].action;
      filter = "";
      page = 0;
      if (a.table === "ledger") {
        tab = "ledger";
        const first =
          current().trajectory[step - 1].observation.result?.records?.[0];
        if (first)
          page = Math.max(
            0,
            Math.floor(
              current().public.ledger.findIndex(
                (r) => r.row_id === first.row_id,
              ) / 8,
            ),
          );
      } else if (a.table === "fx") tab = "policy";
      else if (a.action === "get_document") {
        const i = docs().findIndex((d) => d.doc_id === a.doc_id);
        if (i >= 0) {
          tab = "documents";
          docIndex = i;
        } else tab = "policy";
      } else if (a.table === "invoices" || a.table === "payments") {
        tab = "documents";
        const first =
          current().trajectory[step - 1].observation.result?.records?.[0];
        docIndex = first
          ? Math.max(
              0,
              docs().findIndex((d) => d.doc_id === first.doc_id),
            )
          : a.table === "payments"
            ? current().public.invoices.length
            : 0;
      }
    }
  } else inspector = "results";
  if (!finished() && tab === "comparison") tab = "documents";
  render();
  if (finished()) {
    if (tab === "comparison") $("#source-content").scrollTop = 0;
    $("#results").scrollTop = 0;
    showMobilePane();
  }
  if (inspector === "trace" && matchMedia("(min-width: 801px)").matches)
    document
      .querySelector(".trace-step.current")
      ?.scrollIntoView({ block: "nearest", behavior: "instant" });
}
function pageHeading(kicker, title, description, extra = "") {
  return `<div class='page-heading'><div><span class='section-kicker'>${kicker}</span><h1>${title}</h1><p>${description}</p></div>${extra}</div>`;
}
function verification() {
  const v = data.verification;
  const checks = v.acceptance.cases.filter((x) => x.id.startsWith(checkGroup));
  const picked =
    v.acceptance.cases.find((x) => x.id === selectedCheck) || checks[0];
  const definition = checkDefinitions[picked.id] || {};
  return `<div class='report-page'>${pageHeading("КОНТРОЛЬ КАЧЕСТВА", "Проверяем саму среду.", "От опубликованной методики до результата конкретного теста.", `<a class='secondary-button' href='assets/verification.html' target='_blank' rel='noreferrer'>${icon("external")}Полный отчёт</a>`)}<div class='quality-overview'><div class='quality-score'><strong>${v.acceptance.automatic_score}<small>/90</small></strong><span>Автоматическая часть<br>локальной матрицы</span></div><div class='quality-stat'><strong>${v.unit_tests.passed}<span> / ${v.unit_tests.run}</span></strong><span>Регрессионных тестов</span></div><div class='quality-stat'><strong>${v.sweep_passed}</strong><span>Дополнительных эпизодов</span></div><div class='quality-stat'><strong>${v.mutants_killed}<span> / ${v.selected_mutants}</span></strong><span>Дефектов обнаружено</span></div></div><p class='score-disclosure'>Ещё 10 инженерных баллов оценивает человек. Это результаты нашей проверки по ТЗ, не оценка жюри.</p>
 <div class='audit-workbench'><aside class='audit-groups' aria-label='Группы проверок'><span class='rail-label'>Матрица приёмки</span>${v.acceptance.groups.map((g) => `<button class='group-button ${g.id === checkGroup ? "selected" : ""}' data-group='${g.id}' aria-pressed='${g.id === checkGroup}'><span>${groupNames[g.id]}</span><strong>${g.passed}/${g.total}</strong><i><span></span></i></button>`).join("")}</aside><section class='audit-register'><div class='register-heading'><h2>${groupNames[checkGroup]}</h2>${status(checks.filter((c) => c.status === "passed").length + " пройдено")}</div><div class='check-register'>${checks.map((c) => `<button class='check-row ${c.id === picked.id ? "selected" : ""}' data-check='${c.id}' aria-pressed='${c.id === picked.id}'><span class='check-id'>${c.id}</span><span>${esc(checkDefinitions[c.id]?.title || c.id)}</span>${icon(c.status === "passed" ? "check" : "close")}</button>`).join("")}</div></section><aside class='check-inspector'><span class='section-kicker'>${picked.id} / ${picked.status === "passed" ? "ПРОЙДЕНА" : "ОШИБКА"}</span><h2>${esc(definition.title || picked.id)}</h2><div class='check-duration'>${icon("clock")}${num(picked.seconds, 3)} с</div><h3>Как проверяли</h3><p>${esc(definition.procedure || "Методика опубликована в матрице приёмки.")}</p><h3>Ожидаемый результат</h3><p>${esc(definition.expected || "См. полную матрицу приёмки.")}</p><details><summary>Запись результата JSON</summary>${json(picked)}</details><a href='https://github.com/amurapan/genesis/blob/main/planning/acceptance-matrix.json' target='_blank' rel='noreferrer'>Открыть исходную матрицу</a></aside></div>
 <section class='benchmark-section'><div><span class='section-kicker'>ОБЩИЕ УСЛОВИЯ</span><h2>Четыре политики.<br>Одна выборка.</h2><p>20 одинаковых эпизодов: 5 чистых, 5 с взаимодействиями и 10 остальных.</p></div><div class='benchmark-scroll'><table class='data-table benchmark-table'><thead><tr><th>Политика</th><th>Precision</th><th>Recall</th><th>F1</th><th>Возврат</th><th>Шаги</th></tr></thead><tbody>${v.benchmark.map((x) => `<tr><td>${x.policy}</td>${["precision", "recall", "f1", "reward", "mean_steps"].map((k) => `<td>${num(x[k], k === "mean_steps" ? 1 : 3)}</td>`).join("")}</tr>`).join("")}</tbody></table><p>Средние значения. Для правильного чистого ответа P = R = 0, F1 = 1. Oracle знает эталон и проверяет потолок награды, а не сложность среды.</p></div></section><div class='report-bottom'><span>Предельный эпизод: 2 000 проводок · 200 документов · 12 ошибок · ${v.boundary_run.steps} шагов</span><a href='data/verification.json' download='sled-verification.json'>${icon("download")}Отчёт JSON</a></div></div>`;
}
function architecture() {
  return `<div class='reference-page'>${pageHeading("АРХИТЕКТУРА", "Чёткие границы доверия.", "Агент исследует документы. Эталон и оценка остаются у доверенной стороны.")}
 <div class='trust-diagram'><div class='trust-zone public-zone'><div class='zone-title'>${icon("eye")}Контур расследования</div><div class='system-flow'>${[
   [
     "database",
     "Генератор",
     "Создаёт согласованную историю компании, затем вносит причинные изменения.",
     "Seed + config",
   ],
   [
     "layers",
     "Среда",
     "Выдаёт только запрошенные записи. Считает шаги и сохраняет траекторию.",
     "reset / step",
   ],
   [
     "cpu",
     "Агент",
     "Выбирает инструменты и отправляет выводы в изолированном контейнере.",
     "Docker · без сети",
   ],
 ]
   .map(
     ([i, h, p, s]) =>
       `<article class='flow-card'><span class='flow-icon'>${icon(i)}</span><h2>${h}</h2><p>${p}</p><code>${s}</code></article>`,
   )
   .join(
     "",
   )}</div></div><div class='trust-zone private-zone'><div class='zone-title'>${icon("lock")}Закрытая сторона</div><article class='flow-card'><span class='flow-icon'>${icon("shield")}</span><h2>Оценщик</h2><p>Проверяет тип, сумму, валюту, затронутые ID и полный набор доказательств.</p><code>truth + provenance</code></article><span class='trust-seal'>Агент не видит эталон</span></div></div>
 <div class='architecture-columns'><section><span class='section-kicker'>РАЗРЕШЁННЫЕ ДЕЙСТВИЯ</span><h2>Пять инструментов.</h2><div class='tool-register'>${[
   ["list_records", "Список записей: до 50 строк на страницу."],
   ["get_record", "Одна запись по точному ID."],
   ["get_document", "Первичный документ целиком."],
   ["calculator", "Только десятичная арифметика."],
   ["submit", "Выводы с доказательствами; завершает эпизод."],
 ]
   .map(([a, b]) => `<div><code>${a}</code><p>${b}</p></div>`)
   .join(
     "",
   )}</div><a class='inline-link' href='https://github.com/amurapan/genesis/blob/main/docs/contract.md' target='_blank' rel='noreferrer'>Контракт инструментов</a></section><section><span class='section-kicker'>ПРОВЕРЯЕМЫЙ РЕЗУЛЬТАТ</span><h2>Награда за факты.</h2><div class='reward-equation'>clip(2 × F1 − 1<br>− 0.002 × inspection_steps,<br>−1, 1)</div><p>Исследовательские шаги дают нулевую награду. Повторный вывод считается FP. В закрытом режиме терминальную награду видит только оценщик.</p><p>Независимый валидатор выводит расхождения из публичных документов через точные дроби Fraction. Генератор считает через Decimal.</p><a class='inline-link' href='https://github.com/amurapan/genesis/blob/main/docs/accounting.md' target='_blank' rel='noreferrer'>Финансовые правила</a></section></div><div class='boundary-note'>${icon("info")}<p>Веб-интерфейс воспроизводит публичные записи прогонов. Полная среда, генератор и изолированный оценщик запускаются локально.</p></div></div>`;
}
function guide() {
  return `<div class='reference-page'>${pageHeading("ДЛЯ ЖЮРИ И КОМАНДЫ", "Одно дело. Весь путь.", "Начните с валютного платежа на границе отчётного периода.")}
 <div class='guide-hero'><div class='guide-brief'><span class='brief-label'>ДЕЛО / FX-PERIOD</span><h2>100 USD поступили<br>30 ноября.<br><em>Что попало в книгу?</em></h2><p>Четыре записи, два первичных документа и шесть действий агента.</p><button class='primary-button' data-action='start-guide'>${icon("play")}Открыть это дело</button></div><ol class='guide-steps'>${[
   [
     "Сверьте первичные документы",
     "Счёт — 100 000 KZT. Платёж — 100 USD от 30 ноября. Курс — 450 KZT/USD.",
   ],
   [
     "Откройте проводки",
     "В книге 44 000 KZT датой 1 декабря. Правильное поступление — 45 000 KZT в ноябре.",
   ],
   [
     "Воспроизведите запись",
     "Нижняя панель запускает все шесть шагов. В журнале видны точные запросы и наблюдения.",
   ],
   [
     "Откройте доказательства",
     "FX-расхождение — 1 000 KZT. Ошибка периода — 45 000 KZT. Источник открывается рядом с выводом.",
   ],
 ]
   .map(
     ([h, p], i) =>
       `<li><span>${i + 1}</span><div><h3>${h}</h3><p>${p}</p></div></li>`,
   )
   .join("")}</ol></div>
 <div class='guide-resources'><section class='local-launch'><span class='section-kicker'>НЕЗАВИСИМЫЙ ПОВТОР</span><h2>Запустите всю среду.</h2><p>Linux · Python 3.11 · Docker · cgroup v2</p><pre>git clone https://github.com/amurapan/genesis.git\ncd genesis\nbash verify.sh</pre><button class='secondary-button' data-action='copy-command'>${icon("copy")}Скопировать команды</button><p class='small-note'>Первое получение базового образа может потребовать сеть. С готовыми образами: <code>bash verify.sh --offline</code>.</p></section><section class='guide-media'><span class='section-kicker'>МАТЕРИАЛЫ ПРОЕКТА</span><h2>Демонстрация и презентация.</h2><video controls preload='none' poster='assets/video-poster.png'><source src='assets/demo.mp4' type='video/mp4'>Скачать <a href='assets/demo.mp4'>видео MP4</a></video><p class='small-note'>Запись запуска среды и работы лаборатории. Без озвучки. <a href='assets/narration.txt' download>Текст с таймкодами</a> · <a href='assets/captions.srt' download>Субтитры SRT</a></p><div class='resource-links'><a href='assets/presentation.pdf' target='_blank' rel='noreferrer'>${icon("file")}Презентация PDF</a><a href='assets/presentation.pptx' download>${icon("download")}PPTX</a></div></section></div><div class='boundary-note'>${icon("info")}<p>Поддерживаются счета в базовой валюте, валютные поступления, один счёт на платёж и возвраты переплаты. Налогов, комиссий, переоценки и обучения весов нет.</p></div></div>`;
}
function download(name, value) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2) + "\n"], {
      type: "application/json",
    }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
async function copy(value, message) {
  try {
    await navigator.clipboard.writeText(value);
    toast(message);
  } catch {
    toast(
      "Не удалось скопировать. Используйте адресную строку или выделите текст.",
    );
  }
}
function play() {
  if (timer) {
    stop();
    render();
    return;
  }
  if (finished()) {
    step = 0;
    findingIndex = 0;
  }
  timer = setInterval(() => setStep(step + 1), 1150);
  setStep(step + 1);
}
document.addEventListener("click", (event) => {
  if (event.target.closest(".skip-link")) {
    event.preventDefault();
    $("#main").focus();
    return;
  }
  const el = event.target.closest("button, [data-action]");
  if (!el) return;
  if (el.dataset.case !== undefined) {
    selectCase(Number(el.dataset.case));
    return;
  }
  if (el.dataset.tab) {
    tab = el.dataset.tab;
    page = 0;
    filter = "";
    raw = false;
    selectedSource = "";
    render();
    document
      .querySelector(`[data-tab='${tab}']`)
      ?.focus({ preventScroll: true });
    return;
  }
  if (el.dataset.proof) {
    openSource(el.dataset.proof);
    return;
  }
  if (el.dataset.inspector) {
    inspector = el.dataset.inspector;
    render();
    return;
  }
  if (el.dataset.finding !== undefined) {
    findingIndex = Number(el.dataset.finding);
    if (
      !current().submission.findings[findingIndex].evidence_ids.includes(
        selectedSource,
      )
    )
      selectedSource = "";
    render();
    return;
  }
  if (el.dataset.step) {
    stop();
    setStep(Number(el.dataset.step));
    return;
  }
  if (el.dataset.mobile) {
    mobilePane = el.dataset.mobile;
    render();
    showMobilePane();
    return;
  }
  if (el.dataset.group) {
    checkGroup = el.dataset.group;
    selectedCheck = checkGroup + "01";
    render();
    return;
  }
  if (el.dataset.check) {
    selectedCheck = el.dataset.check;
    render();
    if (matchMedia("(max-width: 700px)").matches)
      document
        .querySelector(".check-inspector")
        ?.scrollIntoView({ block: "start", behavior: "smooth" });
    return;
  }
  switch (el.dataset.action) {
    case "play":
      play();
      break;
    case "next":
      stop();
      setStep(step + 1);
      break;
    case "reset":
      stop();
      tab = "documents";
      docIndex = 0;
      findingIndex = 0;
      page = 0;
      filter = "";
      mobilePane = "sources";
      setStep(0);
      break;
    case "finish":
      stop();
      setStep(current().steps);
      $("#results").scrollTop = 0;
      break;
    case "compare":
      if (!selectedComparison()) break;
      tab = "comparison";
      mobilePane = "sources";
      selectedSource = "";
      render();
      $("#source-content").scrollTop = 0;
      showMobilePane();
      break;
    case "raw":
      raw = !raw;
      render();
      break;
    case "clear-source":
      selectedSource = "";
      raw = false;
      render();
      break;
    case "page-prev":
      page = Math.max(0, page - 1);
      render();
      $("#source-content").scrollTop = 0;
      break;
    case "page-next":
      page++;
      render();
      $("#source-content").scrollTop = 0;
      break;
    case "download-episode":
      download(`sled-${current().id}-public.json`, current().public);
      break;
    case "download-findings":
      download(`sled-${current().id}-findings.json`, current().submission);
      break;
    case "share":
      copy(
        new URL(`lab.html?episode=${current().id}#workspace`, location.href)
          .href,
        "Ссылка на дело скопирована",
      );
      break;
    case "copy-command":
      copy(
        "git clone https://github.com/amurapan/genesis.git\ncd genesis\nbash verify.sh",
        "Команды скопированы",
      );
      break;
    case "start-guide":
      selectCase(0, { reset: true });
      location.hash = "workspace";
      render();
      break;
  }
});
document.addEventListener("change", (e) => {
  if (e.target.id === "episode-select") selectCase(Number(e.target.value));
  if (e.target.id === "comparison-finding" && finished()) {
    findingIndex = Number(e.target.value);
    render();
  }
  if (e.target.id === "document-select") {
    docIndex = Number(e.target.value);
    selectedSource = "";
    raw = false;
    render();
  }
  if (e.target.id === "replay-range") {
    stop();
    setStep(e.target.value);
  }
});
document.addEventListener("input", (e) => {
  if (e.target.id === "ledger-search") {
    filter = e.target.value;
    page = 0;
    selectedSource = "";
    const pos = e.target.selectionStart;
    $("#source-content").innerHTML = ledgerView();
    const input = $("#ledger-search");
    input.focus();
    input.setSelectionRange(pos, pos);
  }
  if (e.target.id === "replay-range")
    $("#scrub-value").textContent = e.target.value;
});
document.addEventListener("keydown", (e) => {
  const list = e.target.closest("[role=tablist]");
  if (!list || !["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key))
    return;
  e.preventDefault();
  const tabs = [...list.querySelectorAll("[role=tab]")];
  const i = tabs.indexOf(e.target);
  const next =
    e.key === "Home"
      ? 0
      : e.key === "End"
        ? tabs.length - 1
        : (i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length;
  const target = tabs[next];
  const key = Object.keys(target.dataset)[0],
    value = target.dataset[key];
  target.click();
  document
    .querySelector(`[data-${key}='${value}']`)
    ?.focus({ preventScroll: true });
});
window.addEventListener("hashchange", () => {
  if (data) {
    render();
    window.scrollTo(0, 0);
  }
});
window.addEventListener("pagehide", stop);
document.addEventListener("visibilitychange", () => {
  if (document.hidden && timer) {
    stop();
    render();
  }
});
hydrate();
try {
  const responses = await Promise.all([
    fetch("data/demo.json"),
    fetch("data/checks.json"),
  ]);
  for (const r of responses) if (!r.ok) throw new Error("HTTP " + r.status);
  [data, checkDefinitions] = await Promise.all(responses.map((r) => r.json()));
  const id = new URL(location.href).searchParams.get("episode");
  caseIndex = Math.max(
    0,
    data.cases.findIndex((c) => c.id === id),
  );
  $("#loading").hidden = true;
  $("#app").hidden = false;
  render();
} catch (error) {
  $("#loading").innerHTML =
    `<h1>Не удалось открыть лабораторию</h1><p>Обновите страницу или откройте <a href='https://github.com/amurapan/genesis'>репозиторий проекта</a>.</p>`;
  console.error(error);
}
