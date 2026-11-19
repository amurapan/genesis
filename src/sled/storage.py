"""Portable episode artifacts and explicit null handling for CSV."""
import csv
import json
from pathlib import Path
from .protocol import dumps, loads


def write_json(path,value):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def export_episode(episode,destination):
    destination=Path(destination); public=destination/'public'; private=destination/'private'
    for key in ['manifest','policy']: write_json(public/(key+'.json'),episode['public'][key])
    for key in ['truth','provenance']: write_json(private/(key+'.json'),episode[key])
    for table in ['invoices','payments']:
        (public/(table+'.jsonl')).write_text(''.join(dumps(r)+'\n' for r in episode['public'][table]))
    fields={'ledger':['row_id','timestamp','account','debit_minor','credit_minor','currency','entity_id','invoice_id','payment_id'],
            'fx':['date','source_currency','target_currency','rate']}
    for table,columns in fields.items():
        with (public/(table+'.csv')).open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=columns); writer.writeheader()
            for row in episode['public'][table]: writer.writerow({k:'null' if v is None else v for k,v in row.items()})


def load_episode(source):
    source=Path(source); public={}
    for key in ['manifest','policy']: public[key]=loads((source/'public'/(key+'.json')).read_text())
    for key in ['invoices','payments']: public[key]=[loads(x) for x in (source/'public'/(key+'.jsonl')).read_text().splitlines() if x]
    for table in ['ledger','fx']:
        with (source/'public'/(table+'.csv')).open(newline='') as f: rows=list(csv.DictReader(f))
        if table=='ledger':
            for row in rows:
                for key in ['debit_minor','credit_minor']: row[key]=int(row[key])
                for key in ['entity_id','invoice_id','payment_id']:
                    if row[key]=='null': row[key]=None
        public[table]=rows
    return dict(public=public,**{key:loads((source/'private'/(key+'.json')).read_text()) for key in ['truth','provenance']})
