"""Build a readable comparison from public evidence and a confirmed finding."""
from datetime import datetime
from decimal import Decimal, localcontext


def money(label, minor, currency, mismatch=False):
    return dict(label=label, minor=minor, currency=currency, mismatch=mismatch)


def value(label, text, mismatch=False):
    return dict(label=label, text=text, mismatch=mismatch)


def card(title, fields, sources):
    return dict(title=title, fields=fields, sources=sources)


def comparison(public, finding):
    kind = finding['type']
    currency = finding['currency']
    difference = finding['claimed_amount_minor']
    evidence = set(finding['evidence_ids'])
    docs = [d for d in public['invoices'] + public['payments'] if 'doc:' + d['doc_id'] in evidence]
    rows = [r for r in public['ledger'] if 'ledger:' + r['row_id'] in evidence]
    affected = set(finding['affected_ids'])
    invoice = next((d for d in docs if 'invoice:' + d.get('invoice_id', '') in affected), None)
    payment = next((d for d in docs if 'payment:' + d.get('payment_id', '') in affected), None)
    ledger_sources = ['ledger:' + r['row_id'] for r in rows]

    if kind == 'duplicate_invoice':
        source_total = invoice['total_minor']
        booked = sum(r['debit_minor'] for r in rows)
        assert booked - source_total == difference
        return dict(
            reference=card('Первичный счёт', [money('Итого по счёту', source_total, currency)], ['doc:' + invoice['doc_id']]),
            booked=card('Признание в книге', [money('Начислено по счёту', booked, currency, True),
                        value('Проводок начисления', str(len(rows)))], ledger_sources),
            note='Сумма начислений превышает сумму первичного счёта.',
        )

    if kind == 'payment_allocation':
        payment_rows = [r for r in rows if r['payment_id'] == payment['payment_id']]
        applied = sum(r['credit_minor'] for r in payment_rows if r['account'] == 'accounts_receivable')
        return dict(
            reference=card('Счёт и первичный платёж', [money('Ожидалось зачесть', applied + difference, currency),
                           money('Получено', payment['amount_minor'], payment['currency'])],
                           ['doc:' + payment['doc_id'], 'doc:' + invoice['doc_id']]),
            booked=card('Распределение в книге', [money('Зачтено по счёту', applied, currency, True)],
                        ['ledger:' + r['row_id'] for r in payment_rows]),
            note='Зачтённая сумма ниже ожидаемой с учётом задолженности по счёту.',
        )

    if kind == 'fx_conversion':
        rate = next(r for r in public['fx'] if f"fx:{r['date']}:{r['source_currency']}:{r['target_currency']}" in evidence)
        exponents = public['manifest']['currency_exponents']
        booked = sum(r['debit_minor'] - r['credit_minor'] for r in rows)
        with localcontext() as context:
            context.prec = 50
            quoted = Decimal(payment['amount_minor']).scaleb(-exponents[payment['currency']]) * Decimal(rate['rate'])
            expected = int(quoted.scaleb(exponents[currency]).to_integral_value(rounding=public['policy']['rounding']))
        assert abs(expected - booked) == difference
        readable_rate = format(Decimal(rate['rate']).normalize(), 'f').replace('.', ',')
        return dict(
            reference=card('Первичный платёж', [money('По курсу на дату платежа', expected, currency),
                           money('Получено', payment['amount_minor'], payment['currency']),
                           value('Курс на ' + datetime.fromisoformat(rate['date']).strftime('%d.%m.%Y'),
                                 f"{readable_rate} {currency} за 1 {payment['currency']}")],
                           ['doc:' + payment['doc_id'], f"fx:{rate['date']}:{rate['source_currency']}:{rate['target_currency']}"]),
            booked=card('Проводка в книге', [money('Записано в книге', booked, currency, True)], ledger_sources),
            note='Сумма в книге отличается от пересчёта по курсу на дату платежа.',
        )

    if kind == 'period_cutoff':
        doc = payment or invoice
        start = datetime.fromisoformat(public['manifest']['period_start'])
        end = datetime.fromisoformat(public['manifest']['period_end'])
        event = datetime.fromisoformat(doc.get('issued_at') or doc['timestamp'])
        posted = datetime.fromisoformat(rows[0]['timestamp'])

        def membership(timestamp):
            return 'В отчётном периоде' if start <= timestamp < end else 'За пределами отчётного периода'

        assert membership(event) != membership(posted)
        return dict(
            reference=card('Первичный платёж' if payment else 'Первичный счёт',
                           [value('Дата события', event.astimezone(start.tzinfo).strftime('%d.%m.%Y')),
                            value('По дате документа', membership(event))], ['doc:' + doc['doc_id'], 'manifest:episode']),
            booked=card('Проводка в книге', [value('Дата проводки', posted.astimezone(start.tzinfo).strftime('%d.%m.%Y'), True),
                        value('По дате проводки', membership(posted))], ledger_sources),
            note='Документ и проводка относятся к разным отчётным периодам.',
        )

    raise ValueError('Unsupported comparison type: ' + kind)
