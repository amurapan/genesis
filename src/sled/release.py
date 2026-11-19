"""Executed release gates and measured diagnostics. No official-score claims."""
import hashlib
import json
import os
from pathlib import Path
import random
import secrets
import statistics
import time
from datetime import datetime, timezone

from . import acceptance
from .corpus import DATA_CONFIGS, holdout
from .environment import AuditEnv, PublicStore
from .generation import generate
from .metadata import ROOT, versions, source_fingerprint
from .mutations import run as mutations
from .oracle import oracle_submission
from .protocol import dumps
from .runner import run_episode
from .scoring import score
from .storage import load_episode, write_json
from .transforms import transform
from .validation import verify_episode


def require(condition, message):
    if not condition: raise AssertionError(message)


def log(message):
    print(message, flush=True)


def public_corpus():
    result=[]
    for name in ['train','dev']:
        config=json.loads((ROOT/f'configs/{name}.json').read_text())
        require(len(config['episodes'])==10,'Ten episodes per public split required')
        for item in config['episodes']:
            directory=ROOT/item['path']
            for file,expected in item['files'].items():
                require(hashlib.sha256((directory/file).read_bytes()).hexdigest()==expected,'Corpus file checksum mismatch')
            e=load_episode(directory)
            require(e==generate(item['seed'],item['config']),'Stored corpus differs from generator')
            verify_episode(e)
            result.append((name,item,e))
    require(len({item['seed'] for _,item,_ in result})==20,'Overlapping public seeds')
    require(len({e['truth']['episode_id'] for _,_,e in result})==20,'Overlapping public episode IDs')
    return result


def scan_trace(trace, closed=False):
    forbidden={'truth','debug_truth','provenance','seed','expected_amount_minor','evidence_sets','issue_id'}
    def visit(value):
        if isinstance(value,dict):
            require(not forbidden.intersection(value),'Private field leaked into observation')
            for v in value.values():visit(v)
        elif isinstance(value,list):
            for v in value:visit(v)
    for row in trace:
        require(set(row)=={'episode_id','step','action','observation','reward','terminated','truncated'},'Bad trajectory schema')
        visit(row['observation'])
        if closed: require(row['reward']==0,'Closed reward leaked')


def replay(e, trace, mode):
    with AuditEnv(mode=mode,episode_factory=lambda s,c:e) as env:
        env.reset(0)
        for row in trace:
            if row['action'] is None:env.truncate()
            else:env.step(row['action'])
        require(env.trajectories==trace,'Trajectory replay differs')


def sweep(seed_base):
    cases=[]; rng=random.Random(seed_base)
    for index in range(200):
        cfg=dict(DATA_CONFIGS[index%20])
        # Predeclared dimensions; this is stress testing, not a learned-model comparison.
        cfg.update(base_currency=['KZT','USD','EUR','JPY','KWD'][index%5],
                   rounding=['ROUND_HALF_EVEN','ROUND_HALF_UP'][index%2],
                   period_start=['2026-02-01T00:00:00+14:00','2026-12-01T00:00:00-12:00','2026-11-01T00:00:00+05:00'][index%3],
                   period_days=[28,31,30][index%3])
        if index%20==14:
            cfg.update(invoice_count=100,split_count=0,refund_count=0,null_count=0,
                       ledger_rows=2000,duplicate_count=3,allocation_count=3,fx_count=3,cutoff_count=3,
                       allocation_mode='missing')
        seed=rng.randrange(2**63)
        e=generate(seed,cfg); verify_episode(e)
        changed=transform(e,fields=acceptance.ALL_IDS,tables=acceptance.ALL_TABLES,seed=index)
        verify_episode(changed)
        a=score(oracle_submission(e['truth']),e['truth'],PublicStore(e['public']).evidence_ids(),4)
        b=score(oracle_submission(changed['truth']),changed['truth'],PublicStore(changed['public']).evidence_ids(),4)
        require(a['f1']==b['f1']==1 and a['reward']==b['reward'],'Sweep transformation mismatch')
        cases.append(dict(index=index,seed=seed,config=cfg,status='passed',
                          ledger_rows=len(e['public']['ledger']),documents=len(e['public']['invoices'])+len(e['public']['payments']),issues=len(e['truth']['issues'])))
    return dict(passed=len(cases),total=200,cases=cases,max_rows=max(c['ledger_rows'] for c in cases),
                max_documents=max(c['documents'] for c in cases),max_issues=max(c['issues'] for c in cases))


def run(output, unit_path=None):
    output=Path(output); output.mkdir(parents=True,exist_ok=True)
    started=time.monotonic(); stamp=datetime.now(timezone.utc).isoformat()
    # The broker and its evaluator share one Linux CPU; agent has a separate 1-CPU quota.
    if hasattr(os,'sched_getaffinity'):
        allowed=os.sched_getaffinity(0); os.sched_setaffinity(0,{min(allowed)})
    unit_path=Path(unit_path or ROOT/'artifacts/unit-tests.json')
    unit=json.loads(unit_path.read_text())
    require(unit['source_sha256']==source_fingerprint(),'Run the unit suite on current source first')
    require(unit['passed']==unit['run'] and not unit['skipped'],'Incomplete regression run')
    info=versions(); write_json(output/'versions.json',info)
    log('Acceptance: 80 cases')
    matrix=acceptance.run(); write_json(output/'acceptance.json',matrix)
    require(matrix['automatic_score']==90,'Acceptance matrix failed; see acceptance.json')
    corpus=public_corpus(); log('Public corpus: 10 train + 10 dev, checksums and regeneration match')
    secret_path=output/'private/holdout-config.json'
    if secret_path.exists(): frozen=json.loads(secret_path.read_text())
    else:
        frozen=dict(seed_base=secrets.randbelow(2**48),sweep_seed=secrets.randbelow(2**48),
                    first_source_sha256=source_fingerprint(),configs=DATA_CONFIGS,
                    note='Locally frozen seeds, inaccessible to the agent; not organizer holdout.')
        write_json(secret_path,frozen)
    require(frozen['configs']==DATA_CONFIGS,'Frozen scenario definitions changed')
    episodes=holdout(frozen['seed_base'])
    require(sum(not e['truth']['issues'] for e in episodes)==5,'Five clean episodes required')
    write_json(output/'split_manifest.json',dict(train=10,dev=10,holdout=20,clean=5,interaction=5,
               holdout_config_sha256=hashlib.sha256(secret_path.read_bytes()).hexdigest()))
    results=[]; all_traces=[]; pairs=[]
    for index,e in enumerate(episodes):
        for policy in ['random','reconciler','flag_all','oracle']:
            r=run_episode(e,policy,'evaluation'); trace=r.pop('trajectories')
            scan_trace(trace,True); results.append(r);all_traces.extend(trace)
            require(not r['truncated'] and r['elapsed_seconds']<60 and r['steps']<=100,'Policy did not finish within resource budget')
            require(r['resources']['observed_peak_upper_bound_bytes']<4*1024**3,'Memory budget exceeded')
            if policy!='oracle':require(r['resources']['agent_cgroup_peak_bytes']>0,'Agent memory measurement unavailable')
        changed=transform(e,fields=acceptance.ALL_IDS,tables=acceptance.ALL_TABLES,seed=index)
        verify_episode(changed)
        a=score(oracle_submission(e['truth']),e['truth'],PublicStore(e['public']).evidence_ids(),4)
        b=score(oracle_submission(changed['truth']),changed['truth'],PublicStore(changed['public']).evidence_ids(),4)
        require(a['f1']==b['f1']==1 and a['reward']==b['reward'],'Holdout pair failed')
        pairs.append(dict(episode_id=e['truth']['episode_id'],passed=True,reward_before=a['reward'],reward_after=b['reward']))
        if (index+1)%5==0:log(f'Policies: {(index+1)*4}/80; paired episodes: {index+1}/20')
    write_json(output/'private/benchmark.json',results)
    (output/'private/closed-trajectories.jsonl').write_text(''.join(dumps(x)+'\n' for x in all_traces))
    write_json(output/'paired.json',pairs)
    open_traces=[]; replayed=[]
    for split,item,e in corpus:
        r=run_episode(e,'reconciler','train'); trace=r['trajectories'];scan_trace(trace)
        require(not r['truncated'],'Public demonstration truncated')
        replay(e,trace,'train');open_traces.extend(trace)
        replayed.append(dict(split=split,episode_id=e['truth']['episode_id'],steps=r['steps'],passed=True))
    (output/'trajectories.jsonl').write_text(''.join(dumps(x)+'\n' for x in open_traces))
    write_json(output/'replay_report.json',replayed)
    write_json(output/'leak_scan.json',dict(open_records=len(open_traces),closed_records=len(all_traces),passed=True,
                method='Recursive forbidden private-field scan plus C20 Docker isolation; not a general information-flow proof'))
    log('Trajectories: 20 public episodes replayed exactly; observation leak scan passed')
    stress=sweep(frozen['sweep_seed']);write_json(output/'private/sweep.json',stress)
    boundary=generate(frozen['sweep_seed'],dict(invoice_count=100,ledger_rows=2000,split_count=0,refund_count=0,null_count=0,
                      duplicate_count=3,allocation_count=3,fx_count=3,cutoff_count=3,allocation_mode='missing'))
    boundary_run=run_episode(boundary,'reconciler','evaluation')
    scan_trace(boundary_run.pop('trajectories'),True)
    require(boundary_run['evaluation']['f1']==1 and not boundary_run['truncated'] and boundary_run['elapsed_seconds']<60
            and boundary_run['steps']<=100 and boundary_run['resources']['observed_peak_upper_bound_bytes']<4*1024**3,
            'Maximum-size resource run failed')
    write_json(output/'boundary_run.json',boundary_run)
    negative=mutations();write_json(output/'mutation_report.json',negative)
    require(negative['killed']==negative['selected_mutants'],'A selected mutation survived')
    log(f'Stress: {stress["passed"]}/200; negative controls: {negative["killed"]}/{negative["selected_mutants"]}')
    diagnostics=[]
    for policy in ['random','reconciler','flag_all','oracle']:
        rows=[r for r in results if r['policy']==policy]
        diagnostics.append(dict(policy=policy,episodes=len(rows),
            **{k:statistics.mean(r['evaluation'][k] for r in rows) for k in ['precision','recall','f1','reward']},
            mean_steps=statistics.mean(r['steps'] for r in rows),max_steps=max(r['steps'] for r in rows),
            mean_seconds=statistics.mean(r['elapsed_seconds'] for r in rows),max_seconds=max(r['elapsed_seconds'] for r in rows),
            max_memory_bytes=max(r['resources']['observed_peak_upper_bound_bytes'] for r in rows)))
    evidence={
        'I01':['README.md: one command','versions.json','acceptance.json','cold run is recorded separately in the final archive'],
        'I02':['versions.json','configs/train.json','configs/dev.json','requirements.lock'],
        'I03':['trajectories.jsonl','replay_report.json','leak_scan.json'],
        'I04':['mutation_report.json','docs/failures.md'],
        'I05':['docs/limitations.md','docs/accounting.md','private/benchmark.json','private/sweep.json'],
    }
    engineering=[dict(id=k,score=None,recommended_after_review=2,status='awaiting_human_review',evidence=v) for k,v in evidence.items()]
    report=dict(project='СЛЕД',version='1.0.0',started_at=stamp,seconds=time.monotonic()-started,
                scope='Local acceptance, not official jury grading',versions=info,unit_tests=unit,
                acceptance=matrix,engineering=engineering,verified_automatic_score=90,automatic_max=90,
                final_score=None,potential_total_after_human_review=100,
                score_note='The frozen matrix reserves I01–I05 for a human. Recommendations are not awarded points.',
                benchmark=diagnostics,paired_passed=len(pairs),sweep_passed=stress['passed'],
                selected_mutants=negative['selected_mutants'],mutants_killed=negative['killed'],
                train_episodes=10,dev_episodes=10,trajectory_records=len(open_traces),
                boundary_run=boundary_run,
                resource_bounds=dict(max_rows=stress['max_rows'],max_documents=stress['max_documents'],max_issues=stress['max_issues'],
                                     host_cpu_affinity=sorted(os.sched_getaffinity(0)),agent_cpu_quota=1,
                                     memory_measurement='Sum of Linux process high water marks and agent cgroup peak; Docker daemon excluded'),
                blockers=[],technical_gates_passed=True)
    write_json(output/'report.json',report)
    from .reporting import render
    render(report,output/'report.html')
    log(f'Completed: 90/90 automatic points; 5 engineering criteria prepared for human review. {output / "report.html"}')
    return report
