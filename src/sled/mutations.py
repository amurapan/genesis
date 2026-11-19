"""Measured negative controls; mutations are applied to isolated copies only."""
import copy
import json
from pathlib import Path
from .generation import generate
from .validation import verify_episode
from .oracle import oracle_submission
from .environment import PublicStore
from .scoring import score
from .metadata import ROOT


def run():
    original=generate(812,{'allocation_mode':'partial'})
    verify_episode(original)
    records=[]
    def corrupt_fx(e):
        for r in e['public']['fx']: r['rate']='999999'
    def corrupt_period(e):
        for r in e['public']['ledger']:
            if r['payment_id']: r['timestamp']='2030-01-01T00:00:00+05:00'
    mutations={
      'fx_rate':corrupt_fx,
      'period_boundary':corrupt_period,
      'truth_amount':lambda e:e['truth']['issues'][0].__setitem__('expected_amount_minor',e['truth']['issues'][0]['expected_amount_minor']+1),
      'missing_issue':lambda e:e['truth']['issues'].pop(),
      'ghost_evidence':lambda e:e['truth']['issues'][0].__setitem__('evidence_sets',[['doc:nonexistent']]),
      'currency_exponent':lambda e:e['public']['manifest']['currency_exponents'].__setitem__('KZT',3),
      'provenance_before':lambda e:e['provenance']['modifications'][0]['before'].__setitem__('debit_minor',-1),
    }
    for name,mutate in mutations.items():
        e=copy.deepcopy(original);mutate(e)
        try:verify_episode(e);killed=False;message='Mutation survived'
        except Exception as exc:killed=True;message=f'{type(exc).__name__}: {exc}'
        records.append(dict(name=name,killed=killed,evidence=message))
    # Execute deliberate scoring mutants in a separate namespace, not in the live evaluator.
    source=(ROOT/'src/sled/scoring.py').read_text()
    e=json.loads((ROOT/'fixtures/manual_errors.json').read_text());answer=oracle_submission(e['truth'])
    known=PublicStore(e['public']).evidence_ids()
    mutants=[('double_tp','tp = len(owner)','tp = len(findings)'),
             ('ignore_currency','and finding["currency"] == issue["currency"]','and True')]
    for name,before,after in mutants:
        assert before in source
        namespace={};exec(compile(source.replace(before,after),f'<{name}>','exec'),namespace)
        payload=copy.deepcopy(answer)
        if name=='double_tp':payload['findings']=[payload['findings'][0]]*10; expected=1
        else:payload['findings'][0]['currency']='USD';expected=1
        actual=namespace['score'](payload,e['truth'],known,0)
        healthy=score(payload,e['truth'],known,0)
        records.append(dict(name=name,killed=actual['tp']!=expected and healthy['tp']==expected,evidence=dict(expected_tp=expected,healthy_tp=healthy['tp'],mutant_tp=actual['tp'])))
    source=(ROOT/'src/sled/environment.py').read_text()
    needle='observation = {"task":'
    assert needle in source
    namespace={'__package__':'sled'}
    exec(compile(source.replace(needle,'observation = {"debug_truth": episode["truth"], "task":',1),'<truth_leak>','exec'),namespace)
    with namespace['AuditEnv'](episode_factory=lambda s,c:e) as env:
        obs,_=env.reset(0)
        leaked='expected_amount_minor' in json.dumps(obs)
    records.append(dict(name='truth_in_observation',killed=leaked,evidence='Observation whitelist rejects a private truth field; mutant contains expected_amount_minor.'))
    return dict(selected_mutants=len(records),killed=sum(r['killed'] for r in records),cases=records,
                scope='Selected negative controls, not an exhaustive mutation-coverage claim')
