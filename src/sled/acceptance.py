"""Executable local acceptance matrix. Failures and skips never receive points."""
import copy
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from .corpus import DATA_CONFIGS
from .environment import AuditEnv, PublicStore
from .generation import generate
from .oracle import oracle_submission
from .protocol import dumps
from .scoring import score
from .storage import export_episode, load_episode
from .transforms import transform
from .validation import verify_episode

ROOT=Path(__file__).resolve().parents[2]
ALL_IDS=['invoice_id','payment_id','row_id','doc_id','entity_id']
ALL_TABLES=['ledger','invoices','payments','fx']


def check(condition,message='Acceptance assertion failed'):
    if not condition: raise AssertionError(message)


def legacy(module,cls,method):
    sys.path.insert(0,str(ROOT/'tests')) if str(ROOT/'tests') not in sys.path else None
    test=getattr(importlib.import_module(module),cls)(method)
    result=unittest.TestResult(); test.run(result)
    check(not result.skipped and not result.errors and not result.failures, str(result.errors+result.failures+result.skipped))


def fixture(clean=False):
    return json.loads((ROOT/'fixtures'/('manual_clean.json' if clean else 'manual_errors.json')).read_text())


def grade(answer,e=None,steps=0,tolerance=0):
    e=e or fixture()
    return score(answer,e['truth'],PublicStore(e['public']).evidence_ids(),steps,tolerance)


def contract(number):
    mapping={1:('test_environment','EnvironmentTests','test_reset_and_readonly_observations'),
             5:('test_environment','EnvironmentTests','test_cursor_cannot_cross_table_or_episode'),
             10:('test_environment','ArithmeticAndTransportTests','test_decimal_arithmetic'),
             11:('test_environment','ArithmeticAndTransportTests','test_calculator_rejects_code_and_resource_attacks'),
             15:('test_environment','EnvironmentTests','test_invalid_submit_terminates_without_diagnostic_leak'),
             19:('test_environment','EnvironmentTests','test_after_terminal_no_second_reward')}
    if number in mapping: return legacy(*mapping[number])
    if number==18:
        legacy('test_environment','EnvironmentTests','test_timeout_uses_empty_answer_formula')
        return legacy('test_container','ContainerTests','test_hung_container_is_stopped')
    if number==20:
        legacy('test_container','ContainerTests','test_agent_sandbox')
        return legacy('test_environment','EnvironmentTests','test_errors_cost_steps_and_are_bounded')
    if number==17:
        legacy('test_environment','EnvironmentTests','test_submit_on_step_100')
        return legacy('test_environment','EnvironmentTests','test_100_inspections_truncates_to_empty')
    e=fixture(); answer=oracle_submission(e['truth'])
    with AuditEnv(episode_factory=lambda s,c:e) as env:
        initial,_=env.reset(0)
        if number==2:
            env.step({'action':'calculator','expression':'1'})
            env.reset(1)
            check(env.steps==0 and not env.trajectories and env.evaluation_result is None)
            legacy('test_environment','EnvironmentTests','test_cursor_cannot_cross_table_or_episode')
        elif number==3:
            actions=[{'action':'list_records','table':'ledger'},{'action':'get_record','table':'invoices','id':'invoice-1'},
                     {'action':'get_document','doc_id':'invoice-doc-1'},{'action':'calculator','expression':'1+2'},
                     {'action':'submit','findings':answer}]
            for a in actions:
                r=env.step(a); dumps(r)
                check(len(r)==5 and isinstance(r[0],dict) and type(r[2]) is bool and type(r[3]) is bool and isinstance(r[4],dict))
        elif number==4:
            for limit in [1,50,0,51,True,'50']:
                r=env.step({'action':'list_records','table':'ledger','limit':limit})[0]
                check(('result' in r)==(type(limit) is int and 1<=limit<=50))
                if 'result' in r: check(len(r['result']['records'])<=limit)
            check(env.steps==6)
        elif number==6:
            with AuditEnv() as other:
                other.reset(19)
                for table,idfield in [('ledger','row_id'),('invoices','invoice_id'),('payments','payment_id'),('fx',None),('policy',None)]:
                    row=other.step({'action':'list_records','table':table,'limit':1})[0]['result']['records'][0]
                    rid=row[idfield] if idfield else ('accounting' if table=='policy' else ':'.join(row[k] for k in ['date','source_currency','target_currency']))
                    check(other.step({'action':'get_record','table':table,'id':rid})[0]['result']==row)
        elif number==7:
            for doc in ['invoice-doc-1','payment-doc-1','policy:accounting','manifest:episode']:
                check('result' in env.step({'action':'get_document','doc_id':doc})[0])
            legacy('test_environment','EnvironmentTests','test_reset_and_readonly_observations')
        elif number==8:
            for a in [{'action':'get_record','table':'ledger','id':'guessed'},{'action':'get_document','doc_id':'truth.json'}]:
                r=env.step(a); check('error' in r[0] and len(dumps(r))<300)
            check(env.inspection_steps==2)
        elif number==9:
            for a in [None,[],{}, {'action':'exec'}, {'action':'list_records','table':[]}, {'action':'calculator','extra':0}]:
                check('error' in env.step(a)[0])
            check(env.steps==6)
            legacy('test_environment','ArithmeticAndTransportTests','test_strict_json')
        elif number==12:
            for _ in range(3): check(env.step({'action':'calculator','expression':'1'})[1]==0)
            check(env.step({'action':'submit','findings':answer})[1]==.994)
        elif number==13:
            for payload in [answer,{}, {'episode_id':answer['episode_id'],'findings':[]}]:
                with AuditEnv(mode='evaluation',episode_factory=lambda s,c:e) as closed:
                    closed.reset(0); r=closed.step({'action':'submit','findings':payload})
                    check(r[1]==0 and r[4]=={} and not any(k in dumps(r) for k in ['matches','precision','expected_amount_minor','issue-1']))
        elif number==14:
            r=env.step({'action':'submit','findings':answer}); check(r[2] and not r[3] and len(env.trajectories)==1)
        elif number==16:
            legacy('test_scoring','ScoringTests','test_invalid_structure_and_boundaries')
            for count in [30,31]:
                a=copy.deepcopy(answer); a['findings']=[a['findings'][0]]*count
                check(grade(a)['valid']==(count==30))
            for count in [10,11]:
                a=copy.deepcopy(answer); f=a['findings'][0]
                f['evidence_ids']+=['policy:accounting']*(count-len(f['evidence_ids']))
                check(grade(a)['valid']==(count==10))
        else: raise AssertionError('Unimplemented contract case')


def reward(number):
    e=fixture(); answer=oracle_submission(e['truth'])
    mapping={1:'test_perfect_and_empty',2:'test_clean_metrics_and_false_accusation',3:'test_clean_metrics_and_false_accusation',
             4:'test_duplicate_findings_are_false_positives',14:'test_maximum_matching_not_greedy',
             16:'test_inspection_cost_and_clipping',17:'test_inspection_cost_and_clipping',20:'test_explanation_order_and_duplicate_ids_do_not_improve_score'}
    if number in mapping: return legacy('test_scoring','ScoringTests',mapping[number])
    f=answer['findings'][0]
    if number==5: f['type']='period_cutoff'
    elif number==6:
        f['affected_ids']+=['invoice:unknown']
    elif number==7:
        f['claimed_amount_minor']+=1
        check(grade(answer,tolerance=1)['tp']==2)
        check(grade(answer,tolerance=0)['tp']==1)
        f['claimed_amount_minor']+=1; check(grade(answer,tolerance=1)['tp']==1); return
    elif number==8: f['currency']='USD'
    elif number==9: f['evidence_ids']=[]
    elif number==10: f['evidence_ids'].pop()
    elif number==11:
        issue=e['truth']['issues'][0]
        alternate=issue['evidence_sets'][0]+['manifest:episode']; issue['evidence_sets'].append(alternate)
        check(grade(answer,e)['tp']==2)
        f['evidence_ids']=alternate; check(grade(answer,e)['tp']==2); return
    elif number==12:
        f['evidence_ids']+=['doc:guessed']; check(grade(answer)['tp']==1)
        f['evidence_ids']=['doc:payment-doc-1']; check(grade(answer)['tp']==1); return
    elif number==13:
        answer['episode_id']='foreign-episode'; check(not grade(answer)['valid']); return
    elif number==15:
        answer['findings']=answer['findings'][:1]
        r=grade(answer); check(r['precision']==1 and r['recall']==.5 and abs(r['f1']-2/3)<1e-12); return
    elif number==18:
        guesses=copy.deepcopy(answer['findings'][:1])*30
        for item in guesses: item['evidence_ids']=[]
        answer['findings']=guesses; check(grade(answer)['valid'] and grade(answer)['reward']==-1)
        clean=fixture(True); answer['episode_id']=clean['truth']['episode_id']; check(grade(answer,clean)['reward']==-1); return
    elif number==19:
        answer['findings']=[f]*31; r=grade(answer); check(not r['valid'] and r['reward']==-1); return
    else: raise AssertionError('Unimplemented reward case')
    r=grade(answer); check(r['tp']==1 and r['fp']==1 and r['fn']==1)


def paired(e,fields=(),tables=()):
    changed=transform(e,fields=fields,tables=tables)
    verify_episode(e); verify_episode(changed)
    a=grade(oracle_submission(e['truth']),e,4); b=grade(oracle_submission(changed['truth']),changed,4)
    for key in ['tp','fp','fn','f1','reward']: check(a[key]==b[key],key)


def generalization(number):
    cfg={'invoice_count':12}; e=generate(761,cfg)
    if number==1: check(dumps(e)==dumps(generate(761,cfg)))
    elif number==2: legacy('test_environment','EnvironmentTests','test_replayed_actions_have_identical_results')
    elif number==3:
        code="from sled.generation import generate; from sled.protocol import dumps; import hashlib; print(hashlib.sha256(dumps(generate(761,{'invoice_count':12})).encode()).hexdigest())"
        child=subprocess.check_output([sys.executable,'-c',code],text=True).strip()
        check(child==hashlib.sha256(dumps(e).encode()).hexdigest())
    elif number==4:
        with AuditEnv() as env:
            a=env.reset(761,cfg); env.reset(12,cfg); check(a==env.reset(761,cfg))
    elif number==5: legacy('test_environment','EnvironmentTests','test_replayed_actions_have_identical_results')
    elif number==6:
        from .policies import RandomExplorer
        traces=[]
        with AuditEnv() as env:
            for _ in range(2):
                obs,_=env.reset(761,cfg); p=RandomExplorer(obs)
                while True:
                    obs,_,done,truncated,_=env.step(p.action(obs))
                    if done or truncated: break
                traces.append(copy.deepcopy(env.trajectories))
        check(traces[0]==traces[1])
    elif number==7:
        with tempfile.TemporaryDirectory() as temp:
            a=Path(temp)/'a'; b=Path(temp)/'b'; export_episode(e,a); export_episode(e,b)
            check(load_episode(a)==e)
            for f in a.rglob('*'):
                if f.is_file(): check(f.read_bytes()==(b/f.relative_to(a)).read_bytes())
    elif number==8:
        with AuditEnv() as a,AuditEnv() as b:
            a.reset(761,cfg); b.reset(999,cfg)
            action={'action':'list_records','table':'ledger','limit':1}
            first=a.step(action); b.step(action); second=a.step(action)
            check(first[0]['result']==second[0]['result'] and a.steps==2 and b.steps==1)
    elif 9<=number<=13: paired(e,fields=[['invoice_id'],['payment_id'],['row_id'],['doc_id'],['entity_id']][number-9])
    elif number==14: paired(e,fields=ALL_IDS)
    elif 15<=number<=18: paired(e,tables=[ALL_TABLES[number-15]])
    elif number==19: paired(e,ALL_IDS,ALL_TABLES)
    elif number==20:
        for i,cfg2 in enumerate([
            {'base_currency':'JPY','rounding':'ROUND_HALF_UP','period_start':'2026-02-01T00:00:00+14:00','period_days':28},
            {'base_currency':'KWD','period_start':'2026-12-01T00:00:00-12:00','fx_mode':'date','cutoff_target':'invoice'},
            {'ledger_rows':2000,'duplicate_count':3,'allocation_count':3,'fx_count':3,'cutoff_count':3,'allocation_mode':'missing'}]):
            paired(generate(870+i,cfg2),ALL_IDS,ALL_TABLES)
    else: raise AssertionError('Unimplemented paired case')


def run():
    matrix=json.loads((ROOT/'planning/acceptance-matrix.json').read_text())
    results=[]
    for group in matrix['groups']:
        for i,definition in enumerate(group['cases'],1):
            started=time.monotonic()
            try:
                if group['id']=='C': contract(i)
                elif group['id']=='D': verify_episode(generate(710000+i-1,DATA_CONFIGS[i-1]))
                elif group['id']=='R': reward(i)
                elif group['id']=='G': generalization(i)
                else: raise AssertionError('Unknown group')
                item=dict(id=definition['id'],status='passed',error=None)
            except Exception as exc:
                item=dict(id=definition['id'],status='failed',error=f'{type(exc).__name__}: {exc}')
            item['seconds']=round(time.monotonic()-started,6); results.append(item)
    groups=[]
    for g in matrix['groups']:
        passed=sum(r['status']=='passed' for r in results if r['id'].startswith(g['id']))
        groups.append(dict(id=g['id'],passed=passed,total=20,score=g['weight']*passed/20))
    return dict(matrix_sha256=hashlib.sha256((ROOT/'planning/acceptance-matrix.json').read_bytes()).hexdigest(),cases=results,groups=groups,
                automatic_score=sum(g['score'] for g in groups),automatic_max=90,scope='local_specification_not_official_jury_suite')
