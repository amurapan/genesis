"""Simple public-record reconciliation policy, independent of the reference validator."""
from datetime import datetime
from decimal import Decimal, localcontext


def reconcile(data, manifest, policy):
    rows=data['ledger']; invs={i['invoice_id']:i for i in data['invoices']}
    base=manifest['base_currency']; exp=manifest['currency_exponents']
    start=datetime.fromisoformat(manifest['period_start']); end=datetime.fromisoformat(manifest['period_end'])
    rates={(r['date'],r['source_currency'],r['target_currency']):r['rate'] for r in data['fx']}
    findings=[]
    def emit(kind,ids,amount,proof,text):
        if len(set(proof))<=10:
            findings.append(dict(type=kind,affected_ids=sorted(ids),claimed_amount_minor=amount,currency=base,evidence_ids=sorted(set(proof)),explanation=text))
    def value(payment):
        if payment['currency']==base: return payment['amount_minor'],[]
        date=datetime.fromisoformat(payment['timestamp']).astimezone(start.tzinfo).date().isoformat()
        key=(date,payment['currency'],base)
        with localcontext() as ctx:
            ctx.prec=50
            result=Decimal(payment['amount_minor'])/10**exp[payment['currency']]*Decimal(rates[key])*10**exp[base]
            result=int(result.to_integral_value(rounding=policy['rounding']))
        return result,['fx:'+':'.join(key)]
    def cutoff(doc,reference,amount,ids,extra=()):
        src=datetime.fromisoformat(doc.get('issued_at',doc.get('timestamp')))
        posted=datetime.fromisoformat(reference['timestamp'])
        if (start<=src<end)!=(start<=posted<end):
            emit('period_cutoff',ids,abs(amount),['doc:'+doc['doc_id'],'ledger:'+reference['row_id'],'manifest:episode','policy:accounting',*extra],
                 'Source event and accounting journal belong to different reporting periods.')
    for iid,inv in invs.items():
        ar=[r for r in rows if r['invoice_id']==iid and r['payment_id'] is None and r['account']=='accounts_receivable']
        extra=sum(r['debit_minor'] for r in ar)-inv['total_minor']
        if extra>0:
            emit('duplicate_invoice',['invoice:'+iid],extra,['doc:'+inv['doc_id'],'policy:accounting']+['ledger:'+r['row_id'] for r in ar],
                 'Total recognition exceeds the primary invoice amount.')
        cutoff(inv,ar[0],inv['total_minor'],['invoice:'+iid])
    settled={iid:0 for iid in invs}; prior={iid:[] for iid in invs}
    for p in sorted(data['payments'],key=lambda p:datetime.fromisoformat(p['timestamp'])):
        group=[r for r in rows if r['payment_id']==p['payment_id']]
        cash=next(r for r in group if r['account']=='cash')
        booked=cash['debit_minor']-cash['credit_minor']; correct,fxproof=value(p)
        if booked!=correct:
            emit('fx_conversion',['payment:'+p['payment_id']],abs(booked-correct),['policy:accounting','doc:'+p['doc_id'],'ledger:'+cash['row_id'],*fxproof],
                 'Booked base-currency cash differs from the source payment converted under the published policy.')
        cutoff(p,cash,correct,['payment:'+p['payment_id']],fxproof)
        if not p['invoice_refs'] or p['amount_minor']<0: continue
        iid=p['invoice_refs'][0]; expected=min(booked,max(0,invs[iid]['total_minor']-settled[iid]))
        actual=sum(r['credit_minor'] for r in group if r['account']=='accounts_receivable')
        if actual<expected:
            emit('payment_allocation',['invoice:'+iid,'payment:'+p['payment_id']],expected-actual,
                 ['policy:accounting','doc:'+invs[iid]['doc_id'],'doc:'+p['doc_id']]+['ledger:'+r['row_id'] for r in group]+prior[iid],
                 'Received book cash was not fully applied to the original invoice outstanding balance.')
        settled[iid]+=expected
        prior[iid]+=['doc:'+p['doc_id'],'ledger:'+cash['row_id']]
    return {'episode_id':manifest['episode_id'],'findings':findings[:30]}
