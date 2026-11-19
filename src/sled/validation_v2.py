"""Independent audit using exact rational arithmetic, not generator conversion."""
from collections import defaultdict
from fractions import Fraction
from .validation import require, timestamp, InvalidData


def audit(public):
    m, policy = public['manifest'], public['policy']
    base=m['base_currency']; exponents=m['currency_exponents']
    start,end=timestamp(m['period_start']),timestamp(m['period_end'])
    require(start<end,'Invalid period')
    require(policy['rounding'] in ('ROUND_HALF_EVEN','ROUND_HALF_UP') and policy['rounding']==m['rounding'],'Invalid rounding policy')
    require(type(policy['amount_tolerance_minor']) is int and policy['amount_tolerance_minor']==0,'Invalid tolerance')
    for currency,exponent in exponents.items():
        require(isinstance(currency,str) and len(currency)==3 and type(exponent) is int and 0<=exponent<=9,'Invalid currency')
    require(base in exponents,'Missing base exponent')
    for table in ['ledger','invoices','payments','fx']:
        require(type(m['record_counts'][table]) is int and m['record_counts'][table]==len(public[table]),'Manifest count mismatch')
    require(type(m['document_count']) is int and m['document_count']==len(public['invoices'])+len(public['payments']),'Document count mismatch')
    require(len(public['ledger'])<=2000 and m['document_count']<=200,'Episode exceeds declared size')
    invs={i['invoice_id']:i for i in public['invoices']}; pays={p['payment_id']:p for p in public['payments']}
    require(len(invs)==len(public['invoices']) and len(pays)==len(public['payments']),'Duplicate document key')
    docs=[d['doc_id'] for d in public['invoices']+public['payments']]
    require(len(set(docs))==len(docs) and all(isinstance(d,str) and d for d in docs),'Invalid document identity')
    fx={}
    for r in public['fx']:
        key=(r['date'],r['source_currency'],r['target_currency'])
        require(key not in fx and r['target_currency']==base and r['source_currency'] in exponents,'Invalid FX key')
        require(isinstance(r['rate'],str),'Rate must be a decimal string')
        try: rate=Fraction(r['rate'])
        except (ValueError,ZeroDivisionError) as exc: raise InvalidData('Invalid rate') from exc
        require(rate>0,'Non-positive FX rate'); fx[key]=rate
    def converted(p):
        require(p['currency'] in exponents,'Unknown payment currency')
        if p['currency']==base: return p['amount_minor'],[]
        date=timestamp(p['timestamp']).astimezone(start.tzinfo).date().isoformat()
        key=(date,p['currency'],base); require(key in fx,'Missing required FX rate')
        value=Fraction(p['amount_minor'])*fx[key]*Fraction(10**exponents[base],10**exponents[p['currency']])
        q,r=divmod(abs(value.numerator),value.denominator)
        if 2*r>value.denominator or (2*r==value.denominator and (policy['rounding']=='ROUND_HALF_UP' or q%2)): q+=1
        return q if value>=0 else -q,['fx:'+':'.join(key)]
    rows=public['ledger']; by_invoice=defaultdict(list); by_payment=defaultdict(list)
    require(len({r['row_id'] for r in rows})==len(rows),'Duplicate row ID')
    for r in rows:
        require(isinstance(r['row_id'],str) and r['row_id'],'Invalid row ID')
        require(r['currency']==base,'Ledger currency must be base')
        require(r['account'] in ['cash','accounts_receivable','revenue','unapplied_cash'],'Invalid account')
        require(type(r['debit_minor']) is int and type(r['credit_minor']) is int,'Non-integer money')
        require(r['debit_minor']>=0 and r['credit_minor']>=0 and bool(r['debit_minor'])!=bool(r['credit_minor']),'Invalid ledger direction')
        timestamp(r['timestamp'])
        iid,pid=r['invoice_id'],r['payment_id']
        require(iid is None or iid in invs,'Unknown invoice reference')
        require(pid is None or pid in pays,'Unknown payment reference')
        require(iid is not None or pid is not None,'Unattributed journal')
        require(r['entity_id']==(invs[iid]['entity_id'] if iid else None),'Wrong entity link')
        if pid is None: by_invoice[iid].append(r)
        else: by_payment[pid].append(r)
    require(sum(r['debit_minor']-r['credit_minor'] for r in rows)==0,'Trial balance failed')
    output=[]
    def finding(kind,ids,amount,proof):
        proof=sorted(set(proof))
        require(type(amount) is int and amount>0 and len(proof)<=10,'Invalid derived issue')
        output.append(dict(type=kind,affected_ids=sorted(ids),expected_amount_minor=amount,currency=base,required_evidence=proof))
    def cutoff(document,group,reference,amount,affected,fx_ids=()):
        dates={timestamp(r['timestamp']) for r in group}
        require(len(dates)==1,'Journal spans multiple posting timestamps')
        posted=next(iter(dates)); source=timestamp(document.get('issued_at',document.get('timestamp')))
        if (start<=posted<end)!=(start<=source<end):
            finding('period_cutoff',[affected],abs(amount),['doc:'+document['doc_id'],'ledger:'+reference['row_id'],'policy:accounting','manifest:episode',*fx_ids])
    for iid,inv in invs.items():
        require(inv['currency']==base and type(inv['total_minor']) is int and inv['total_minor']>0,'Invalid invoice amount or denomination')
        require(timestamp(inv['due_at'])>=timestamp(inv['issued_at']),'Invalid due date')
        require(bool(inv['line_items']),'Missing line items')
        for line in inv['line_items']:
            require(all(type(line[k]) is int for k in ['quantity','unit_price_minor','total_minor']),'Non-integer line item')
            require(line['quantity']>0 and line['unit_price_minor']>0 and line['quantity']*line['unit_price_minor']==line['total_minor'],'Line total mismatch')
        require(sum(x['total_minor'] for x in inv['line_items'])==inv['total_minor'],'Invoice total mismatch')
        group=by_invoice[iid]; ar=[r for r in group if r['account']=='accounts_receivable']; rev=[r for r in group if r['account']=='revenue']
        require(ar and len(ar)+len(rev)==len(group),'Invoice journal missing or invalid')
        require(all(r['credit_minor']==0 and r['debit_minor']==inv['total_minor'] for r in ar),'Invoice recognition amount invalid')
        require(all(r['debit_minor']==0 for r in rev),'Wrong revenue direction')
        booked=sum(r['debit_minor'] for r in ar)
        require(booked==sum(r['credit_minor'] for r in rev),'Invoice journal unbalanced')
        if booked>inv['total_minor']:
            finding('duplicate_invoice',['invoice:'+iid],booked-inv['total_minor'],['policy:accounting','doc:'+inv['doc_id']]+['ledger:'+r['row_id'] for r in ar])
        # All AR lines have the same timestamp; either is an independently sufficient witness.
        cutoff(inv,group,ar[0],inv['total_minor'],'invoice:'+iid)
    outstanding={iid:i['total_minor'] for iid,i in invs.items()}; surplus=defaultdict(int); prior=defaultdict(list); seen=set()
    for p in sorted(pays.values(),key=lambda x:timestamp(x['timestamp'])):
        require(type(p['amount_minor']) is int and p['amount_minor']!=0,'Invalid payment amount')
        refs=p['invoice_refs']; require(refs is None or (isinstance(refs,list) and len(refs)==1 and refs[0] in invs),'Invalid payment reference')
        iid=refs[0] if refs else None; instant=timestamp(p['timestamp'])
        if iid:
            require(instant>=timestamp(invs[iid]['issued_at']),'Payment precedes invoice')
            require((iid,instant) not in seen,'Ambiguous simultaneous payments'); seen.add((iid,instant))
        correct,fx_ids=converted(p)
        group=by_payment[p['payment_id']]
        require(group and all(r['invoice_id']==iid for r in group),'Payment group missing or linkage invalid')
        cash=[r for r in group if r['account']=='cash']; ar=[r for r in group if r['account']=='accounts_receivable']; clearing=[r for r in group if r['account']=='unapplied_cash']
        require(len(cash)==1 and len(group)==len(cash)+len(ar)+len(clearing),'Invalid payment journal')
        booked=cash[0]['debit_minor']-cash[0]['credit_minor']
        if p['amount_minor']>0:
            require(booked>0 and all(r['debit_minor']==0 for r in ar+clearing),'Wrong receipt direction')
            applied=sum(r['credit_minor'] for r in ar); unapplied=sum(r['credit_minor'] for r in clearing)
            require(applied+unapplied==booked,'Receipt unbalanced')
            expected=min(booked,outstanding[iid]) if iid else 0
            require(applied<=expected,'Over-allocation not one of the declared errors')
            if applied<expected:
                proof=['policy:accounting','doc:'+invs[iid]['doc_id'],'doc:'+p['doc_id']]+['ledger:'+r['row_id'] for r in group]+prior[iid]
                finding('payment_allocation',['invoice:'+iid,'payment:'+p['payment_id']],expected-applied,proof)
            if iid:
                outstanding[iid]-=expected
                prior[iid]+=['doc:'+p['doc_id'],'ledger:'+cash[0]['row_id']]
            surplus[iid]+=booked-expected
        else:
            require(p['currency']==base and booked<0 and not ar,'Refund denomination or direction unsupported')
            require(all(r['credit_minor']==0 for r in clearing) and sum(r['debit_minor'] for r in clearing)==-booked,'Refund unbalanced')
            require(-booked<=surplus[iid],'Refund exceeds legitimate unapplied surplus'); surplus[iid]+=booked
        if booked!=correct:
            require(p['currency']!=base,'Base cash amount mismatch is not an FX error')
            finding('fx_conversion',['payment:'+p['payment_id']],abs(booked-correct),['policy:accounting','doc:'+p['doc_id'],'ledger:'+cash[0]['row_id'],*fx_ids])
        cutoff(p,group,cash[0],correct,'payment:'+p['payment_id'],fx_ids)
    return output
