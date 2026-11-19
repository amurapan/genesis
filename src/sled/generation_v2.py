"""Causal multi-currency generator; no dependency on audit or scoring code."""
import copy
import hashlib
import random
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from .protocol import dumps

VERSION = '1.0.0'
EXPONENTS = {'KZT': 2, 'USD': 2, 'EUR': 2, 'JPY': 0, 'KWD': 3}
# Fictional price relationships, not market data.
VALUES = {'KZT': '1', 'USD': '500', 'EUR': '550', 'JPY': '3.5', 'KWD': '1600'}
POLICY = {
    'profile': 'receivables_v2',
    'supported_issue_types': ['duplicate_invoice', 'payment_allocation', 'fx_conversion', 'period_cutoff'],
    'invoice_recognition': 'Recognize each original base-currency invoice once at issued_at',
    'allocation': 'Allocate booked base-currency cash up to the original invoice outstanding balance; previous receipts reduce that balance before allocation faults',
    'allocation_order': 'Chronological source payment timestamps, unique per invoice',
    'currency_scope': 'Invoices are base-denominated; receipts may use any declared currency',
    'fx_date': 'Source payment timestamp converted to the fixed business offset of period_start',
    'refunds': 'Negative base-currency payments refund previously unapplied surplus only',
    'missing_refs': 'Null invoice_refs means unapplied cash, not an inferred invoice link',
    'cutoff': 'Compare membership in [period_start, period_end) of the source document and journal timestamp',
    'rounding': 'ROUND_HALF_EVEN', 'amount_tolerance_minor': 0,
    'period_bounds': 'start_inclusive_end_exclusive',
}


def generate(seed, config=None):
    if type(seed) is not int or not 0 <= seed < 2**64:
        raise ValueError('seed must be an unsigned 64-bit integer')
    if config is not None and not isinstance(config, dict):
        raise ValueError('config must be an object')
    raw = config or {}
    defaults = dict(invoice_count=40, duplicate_count=1, allocation_count=1, fx_count=1,
                    cutoff_count=1, split_count=2, refund_count=2, null_count=1,
                    foreign_payments=True, allocation_mode='partial', fx_mode='rate',
                    cutoff_direction='late', cutoff_target='payment', interaction=True,
                    base_currency='KZT', period_start='2026-11-01T00:00:00+05:00',
                    period_days=30, ledger_rows=None, rounding='ROUND_HALF_EVEN')
    if set(raw)-set(defaults):
        raise ValueError('Unknown configuration field')
    # Tiny configurations can explicitly request distractors; defaults fit the size.
    n = raw.get('invoice_count', 40)
    if type(n) is not int or not 1 <= n <= 100:
        raise ValueError('invoice_count must be 1..100')
    room = 200-2*n
    defaults.update(split_count=min(2,n//5,room), refund_count=min(2,n//5,max(0,room-2)),
                    null_count=min(1,n//10,max(0,room-4)))
    cfg = defaults | raw
    counts = ['duplicate_count','allocation_count','fx_count','cutoff_count','split_count','refund_count','null_count']
    if any(type(cfg[k]) is not int or not 0 <= cfg[k] <= n for k in counts):
        raise ValueError('Invalid scenario count')
    if sum(cfg[k] for k in counts[:4]) > 12 or 2*n+sum(cfg[k] for k in counts[4:]) > 200:
        raise ValueError('Episode exceeds document or issue budget')
    if type(cfg['foreign_payments']) is not bool or type(cfg['interaction']) is not bool:
        raise ValueError('Boolean options required')
    for key, choices in [('base_currency',EXPONENTS),('rounding',['ROUND_HALF_EVEN','ROUND_HALF_UP']),
                         ('allocation_mode',['partial','missing']),('fx_mode',['rate','date']),
                         ('cutoff_direction',['early','late']),('cutoff_target',['payment','invoice'])]:
        if cfg[key] not in choices:
            raise ValueError('Invalid '+key)
    if type(cfg['period_days']) is not int or not 7 <= cfg['period_days'] <= 62:
        raise ValueError('period_days must be 7..62')
    start = datetime.fromisoformat(cfg['period_start'])
    if start.utcoffset() is None or start.time().isoformat() != '00:00:00':
        raise ValueError('period_start must be offset-aware midnight')
    end = start+timedelta(days=cfg['period_days'])
    base = cfg['base_currency']
    foreign = [c for c in EXPONENTS if c != base]
    if cfg['fx_count'] and not cfg['foreign_payments']:
        raise ValueError('FX faults need foreign payments')

    def rng(label):
        material = dumps([VERSION, seed, cfg, label]).encode()
        return random.Random(int.from_bytes(hashlib.sha256(material).digest(),'big'))
    ids, world, faults, order = (rng(x) for x in ['ids','world','faults','order'])
    def uid(prefix): return f'{prefix}_{ids.getrandbits(128):032x}'
    eid = uid('ep')
    fx = []
    for day in range(-2,cfg['period_days']+3):
        for currency in foreign:
            with localcontext() as ctx:
                ctx.prec = 50
                rate = (Decimal(VALUES[currency])/Decimal(VALUES[base]) * (Decimal(10000+3*day)/10000)).quantize(Decimal('.00000001'))
            fx.append(dict(date=(start+timedelta(days=day)).date().isoformat(),source_currency=currency,target_currency=base,rate=format(rate,'f')))
    rates = {(r['date'],r['source_currency']):r['rate'] for r in fx}
    def convert(amount,currency,ts,rate=None):
        if currency == base: return amount
        date = datetime.fromisoformat(ts).astimezone(start.tzinfo).date().isoformat()
        with localcontext() as ctx:
            ctx.prec = 50
            value = Decimal(amount)*Decimal(rate or rates[(date,currency)])*10**EXPONENTS[base]/10**EXPONENTS[currency]
            return int(value.to_integral_value(rounding=cfg['rounding']))
    def source_amount(target,currency,ts):
        if currency == base: return target
        date = datetime.fromisoformat(ts).date().isoformat()
        with localcontext() as ctx:
            ctx.prec=50
            return max(1,int((Decimal(target)*10**EXPONENTS[currency]/10**EXPONENTS[base]/Decimal(rates[(date,currency)])).to_integral_value(rounding=cfg['rounding'])))

    selection=list(range(n)); faults.shuffle(selection)
    refund_set=set(selection[-cfg['refund_count']:] if cfg['refund_count'] else [])
    candidates=[i for i in selection if i not in refund_set]
    if max(cfg[k] for k in counts[:4]) > len(candidates):
        raise ValueError('Not enough non-refund events for requested faults')
    split_set=set(candidates[:cfg['split_count']])
    if len(split_set) < cfg['split_count']:
        raise ValueError('Not enough events for split payments')
    dup_set=set(candidates[:cfg['duplicate_count']])
    alloc_set=set(candidates[:cfg['allocation_count']])
    offset=max(cfg['duplicate_count'],cfg['allocation_count'])
    fx_order=candidates[offset:]+candidates[:offset]
    fx_set=set(fx_order[:cfg['fx_count']])
    cutoff_order=fx_order if cfg['interaction'] else fx_order[cfg['fx_count']:]+fx_order[:cfg['fx_count']]
    cutoff_set=set(cutoff_order[:cfg['cutoff_count']])
    if not cfg['interaction']:
        total=sum(cfg[k] for k in counts[:4])
        if total > len(candidates): raise ValueError('Independent faults require distinct events')
        a=cfg['duplicate_count']; b=a+cfg['allocation_count']; c=b+cfg['fx_count']
        alloc_set=set(candidates[a:b]); fx_set=set(candidates[b:c]); cutoff_set=set(candidates[c:total])

    invoices=[]; payments=[]; ledger=[]; events={}; correct_values={}
    def row(account,debit,credit,invoice,payment=None,ts=None):
        return dict(row_id=uid('r'),timestamp=ts or invoice['issued_at'],account=account,debit_minor=debit,
                    credit_minor=credit,currency=base,entity_id=invoice['entity_id'] if invoice else None,
                    invoice_id=invoice['invoice_id'] if invoice else None,payment_id=payment)
    def receipt(invoice,currency,amount,ts,available):
        payment=dict(doc_id=uid('d'),payment_id=uid('p'),timestamp=ts,currency=currency,amount_minor=amount,
                     invoice_refs=[invoice['invoice_id']] if invoice else None)
        payments.append(payment)
        booked=convert(amount,currency,ts); correct_values[payment['payment_id']]=booked
        if booked < 0:
            group=[row('cash',0,-booked,invoice,payment['payment_id'],ts),row('unapplied_cash',-booked,0,invoice,payment['payment_id'],ts)]
        else:
            applied=min(booked,available) if invoice else 0
            group=[row('cash',booked,0,invoice,payment['payment_id'],ts)]
            if applied: group.append(row('accounts_receivable',0,applied,invoice,payment['payment_id'],ts))
            if booked-applied: group.append(row('unapplied_cash',0,booked-applied,invoice,payment['payment_id'],ts))
        ledger.extend(group)
        return payment,group
    for i in range(n):
        amount=world.randrange(100000,900001)
        if i and i%5==0: amount=invoices[-1]['total_minor']
        issued=(start+timedelta(days=1,hours=i%20)).isoformat()
        inv=dict(doc_id=uid('d'),invoice_id=uid('i'),entity_id=uid('e'),issued_at=issued,
                 due_at=(end+timedelta(days=7)).isoformat(),currency=base,total_minor=amount,
                 line_items=[dict(description=f'Fictional service {world.choice(["Orion","Mira","Vega","Atlas"])}',quantity=1,unit_price_minor=amount,total_minor=amount)])
        invoices.append(inv)
        ar=row('accounts_receivable',amount,0,inv); rev=row('revenue',0,amount,inv)
        ledger.extend([ar,rev])
        ts=(end-timedelta(seconds=1+i)).isoformat()
        previous=[]; available=amount
        if i in split_set:
            p,g=receipt(inv,base,amount//4,(end-timedelta(days=2,seconds=i)).isoformat(),available)
            available-=p['amount_minor']; previous=[p]
        if i in refund_set:
            p,g=receipt(inv,base,amount+amount//5,(end-timedelta(days=2,seconds=i)).isoformat(),amount)
            receipt(inv,base,-(amount//5),ts,0)
        else:
            currency=foreign[i%len(foreign)] if cfg['foreign_payments'] and (i%2==0 or i in fx_set) else base
            p,g=receipt(inv,currency,source_amount(amount//2,currency,ts),ts,available)
        events[i]=dict(invoice=inv,payment=p,group=g,ar=ar,rev=rev,previous=previous,available=available)
    for i in range(cfg['null_count']):
        receipt(None,base,world.randrange(1000,10000),(start+timedelta(days=3,seconds=i)).isoformat(),0)

    extra=2*len(dup_set)+(len(alloc_set) if cfg['allocation_mode']=='partial' else 0)
    target=cfg['ledger_rows'] if cfg['ledger_rows'] is not None else max(200,3*len(invoices+payments)+50)
    if type(target) is not int or not len(ledger)+extra <= target <= 2000:
        raise ValueError('ledger_rows outside feasible range or above 2000')
    needed=target-extra-len(ledger)
    for event in events.values():
        if not needed: break
        original=event['rev']; pieces=min(needed,original['credit_minor']-1)
        original['credit_minor']-=pieces
        for _ in range(pieces): ledger.append(dict(original,row_id=uid('r'),credit_minor=1))
        needed-=pieces
    if needed: raise ValueError('Insufficient revenue to split ledger rows')
    baseline=copy.deepcopy(ledger); changes=[]; injected=[]
    def add(r,cause):
        ledger.append(r); changes.append(dict(operation='add',table='ledger',before=None,after=copy.deepcopy(r),cause=cause))
    def update(r,values,cause):
        before=copy.deepcopy(r); r.update(values)
        changes.append(dict(operation='update',table='ledger',before=before,after=copy.deepcopy(r),cause=cause))
    def remove(r,cause):
        changes.append(dict(operation='delete',table='ledger',before=copy.deepcopy(r),after=None,cause=cause)); ledger.remove(r)
    # Conversion precedes allocation, so each control has a non-overlapping meaning.
    for i in sorted(fx_set):
        e=events[i]; p=e['payment']; date=datetime.fromisoformat(p['timestamp']).date()
        if cfg['fx_mode']=='date': wrong=rates[((date-timedelta(days=1)).isoformat(),p['currency'])]
        else: wrong=str(Decimal(rates[(date.isoformat(),p['currency'])])*Decimal('1.013'))
        wrong_base=convert(p['amount_minor'],p['currency'],p['timestamp'],wrong)
        good=correct_values[p['payment_id']]
        if wrong_base==good: raise ValueError('FX change is not observable')
        # Ordinary target receipts remain below the outstanding amount.
        if wrong_base>=e['available']: raise ValueError('FX target would overpay invoice')
        for r in e['group']:
            update(r,{'debit_minor':wrong_base} if r['account']=='cash' else {'credit_minor':wrong_base},'fx_conversion')
        injected.append(('fx_conversion',e,abs(wrong_base-good)))
    for i in sorted(dup_set):
        e=events[i]; inv=e['invoice']
        add(row('accounts_receivable',inv['total_minor'],0,inv),'duplicate_invoice')
        add(row('revenue',0,inv['total_minor'],inv),'duplicate_invoice')
        injected.append(('duplicate_invoice',e,inv['total_minor']))
    for i in sorted(alloc_set):
        e=events[i]; p=e['payment']; ar=next(r for r in e['group'] if r['account']=='accounts_receivable')
        missing=ar['credit_minor'] if cfg['allocation_mode']=='missing' else faults.randrange(1,max(2,ar['credit_minor']//2))
        if missing==ar['credit_minor']: remove(ar,'payment_allocation'); e['group'].remove(ar)
        else: update(ar,{'credit_minor':ar['credit_minor']-missing},'payment_allocation')
        clearing=row('unapplied_cash',0,missing,e['invoice'],p['payment_id'],p['timestamp'])
        add(clearing,'payment_allocation'); e['group'].append(clearing)
        injected.append(('payment_allocation',e,missing))
    for i in sorted(cutoff_set):
        e=events[i]
        new_time=(start-timedelta(seconds=1+i) if cfg['cutoff_direction']=='early' else end+timedelta(seconds=i)).isoformat()
        if cfg['cutoff_target']=='invoice':
            group=[r for r in ledger if r['invoice_id']==e['invoice']['invoice_id'] and r['payment_id'] is None]
            amount=e['invoice']['total_minor']
        else: group=e['group']; amount=abs(correct_values[e['payment']['payment_id']])
        for r in group: update(r,{'timestamp':new_time},'period_cutoff')
        injected.append(('period_cutoff',e,amount))

    def fxproof(p):
        date=datetime.fromisoformat(p['timestamp']).astimezone(start.tzinfo).date().isoformat()
        return [] if p['currency']==base else [f'fx:{date}:{p["currency"]}:{base}']
    issues=[]
    for kind,e,amount in injected:
        inv,p=e['invoice'],e['payment']
        proof=['policy:accounting']; affected=[]
        if kind=='duplicate_invoice':
            affected=['invoice:'+inv['invoice_id']]; proof+=['doc:'+inv['doc_id']]
            proof+=['ledger:'+r['row_id'] for r in ledger if r['invoice_id']==inv['invoice_id'] and r['payment_id'] is None and r['account']=='accounts_receivable']
        elif kind=='payment_allocation':
            affected=['invoice:'+inv['invoice_id'],'payment:'+p['payment_id']]
            proof+=['doc:'+inv['doc_id'],'doc:'+p['doc_id']]+['ledger:'+r['row_id'] for r in e['group']]
            for prior in e['previous']:
                proof+=['doc:'+prior['doc_id']]+['ledger:'+r['row_id'] for r in ledger if r['payment_id']==prior['payment_id'] and r['account']=='cash']
        elif kind=='fx_conversion':
            affected=['payment:'+p['payment_id']]
            proof+=['doc:'+p['doc_id']]+['ledger:'+r['row_id'] for r in e['group'] if r['account']=='cash']+fxproof(p)
        else:
            proof+=['manifest:episode']
            if cfg['cutoff_target']=='invoice':
                affected=['invoice:'+inv['invoice_id']]; proof+=['doc:'+inv['doc_id'],'ledger:'+e['ar']['row_id']]
            else:
                affected=['payment:'+p['payment_id']]
                proof+=['doc:'+p['doc_id']]+['ledger:'+r['row_id'] for r in e['group'] if r['account']=='cash']+fxproof(p)
        if len(set(proof))>10: raise ValueError('Proof exceeds action contract')
        proofs=[sorted(set(proof))]
        if kind=='period_cutoff' and cfg['cutoff_target']=='invoice':
            witnesses=['ledger:'+r['row_id'] for r in ledger if r['invoice_id']==inv['invoice_id'] and r['payment_id'] is None and r['account']=='accounts_receivable']
            proofs=[sorted((set(proof)-set(witnesses))|{w}) for w in witnesses]
        issues.append(dict(issue_id=uid('issue'),type=kind,affected_ids=sorted(affected),expected_amount_minor=amount,currency=base,evidence_sets=proofs))
    for table in (ledger,invoices,payments,fx): order.shuffle(table)
    policy=dict(POLICY,rounding=cfg['rounding'])
    manifest=dict(schema_version='1.0.0',generator_version=VERSION,episode_id=eid,base_currency=base,
                  currency_exponents=dict(EXPONENTS),period_start=start.isoformat(),period_end=end.isoformat(),
                  timezone='UTC'+start.strftime('%z'),rounding=cfg['rounding'],
                  record_counts=dict(ledger=len(ledger),invoices=len(invoices),payments=len(payments),fx=len(fx)),document_count=len(invoices)+len(payments))
    return dict(public=dict(manifest=manifest,policy=policy,ledger=ledger,invoices=invoices,payments=payments,fx=fx),
                truth=dict(schema_version='1.0.0',episode_id=eid,issues=issues),
                provenance=dict(generator_version=VERSION,seed=seed,config=cfg,baseline_ledger=baseline,modifications=changes))
