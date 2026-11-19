"""Regenerate the public file schemas without runtime dependencies."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'schemas'
HEADER={'$schema':'https://json-schema.org/draft/2020-12/schema'}
def obj(props,required=None):return {'type':'object','properties':props,'required':list(props) if required is None else required,'additionalProperties':False}
def ref(name):return {'$ref':name+'.schema.json'}
def write(name,schema):(OUT/(name+'.schema.json')).write_text(json.dumps(HEADER|schema,indent=2)+'\n')
ID={'type':'string','minLength':1}; NULLID={'type':['string','null'],'minLength':1}
MONEY={'type':'integer'}; POS={'type':'integer','minimum':1}; NONNEG={'type':'integer','minimum':0}
CURRENCY={'type':'string','pattern':'^[A-Z]{3}$'}; TIME={'type':'string','format':'date-time'}
KINDS=['duplicate_invoice','payment_allocation','fx_conversion','period_cutoff']
write('ledger-record',obj({'row_id':ID,'timestamp':TIME,'account':{'enum':['cash','accounts_receivable','revenue','unapplied_cash']},'debit_minor':NONNEG,'credit_minor':NONNEG,'currency':CURRENCY,'entity_id':NULLID,'invoice_id':NULLID,'payment_id':NULLID}))
line=obj({'description':{'type':'string'},'quantity':POS,'unit_price_minor':POS,'total_minor':POS})
write('invoice',obj({'doc_id':ID,'invoice_id':ID,'entity_id':ID,'issued_at':TIME,'due_at':TIME,'currency':CURRENCY,'total_minor':POS,'line_items':{'type':'array','minItems':1,'items':line}}))
write('payment',obj({'doc_id':ID,'payment_id':ID,'timestamp':TIME,'currency':CURRENCY,'amount_minor':MONEY|{'not':{'const':0}},'invoice_refs':{'anyOf':[{'type':'null'},{'type':'array','minItems':1,'maxItems':1,'items':ID}]}}))
write('fx-record',obj({'date':{'type':'string','format':'date'},'source_currency':CURRENCY,'target_currency':CURRENCY,'rate':{'type':'string','pattern':r'^[0-9]+(?:\.[0-9]+)?$','not':{'pattern':r'^0+(?:\.0+)?$'}}}))
policy=obj({'profile':{'enum':['domestic_receivables_v1','receivables_v2']},'supported_issue_types':{'type':'array','uniqueItems':True,'items':{'enum':KINDS}},**{k:{'type':'string'} for k in ['invoice_recognition','allocation','allocation_order','currency_scope','fx_date','refunds','missing_refs','cutoff']},'rounding':{'enum':['ROUND_HALF_EVEN','ROUND_HALF_UP']},'amount_tolerance_minor':NONNEG,'period_bounds':{'const':'start_inclusive_end_exclusive'}},['profile','supported_issue_types','invoice_recognition','allocation','allocation_order','currency_scope','rounding','amount_tolerance_minor','period_bounds'])
policy['allOf']=[{'if':{'properties':{'profile':{'const':'receivables_v2'}}},'then':{'required':['fx_date','refunds','missing_refs','cutoff']}}]
write('policy',policy)
m=json.loads((OUT/'manifest.schema.json').read_text());m['properties']['rounding']={'enum':['ROUND_HALF_EVEN','ROUND_HALF_UP']};m['properties']['record_counts']['properties']['ledger']['maximum']=2000;m['properties']['document_count']['maximum']=200;write('manifest',m)
issue=obj({'issue_id':ID,'type':{'enum':KINDS},'affected_ids':{'type':'array','minItems':1,'items':ID},'expected_amount_minor':POS,'currency':CURRENCY,'evidence_sets':{'type':'array','minItems':1,'items':{'type':'array','minItems':1,'maxItems':10,'items':ID}}})
write('truth',obj({'schema_version':{'const':'1.0.0'},'episode_id':ID,'issues':{'type':'array','maxItems':12,'items':issue}}))
change=obj({'operation':{'enum':['add','update','delete']},'table':{'const':'ledger'},'before':{'anyOf':[{'type':'null'},ref('ledger-record')]},'after':{'anyOf':[{'type':'null'},ref('ledger-record')]},'cause':{'enum':KINDS}})
write('provenance',obj({'generator_version':ID,'seed':{'type':'integer','minimum':0},'config':{'type':'object'},'authored':ID,'baseline_ledger':{'type':'array','items':ref('ledger-record')},'modifications':{'type':'array','items':change}},['baseline_ledger','modifications']))
public=obj({'manifest':ref('manifest'),'policy':ref('policy'),'ledger':{'type':'array','items':ref('ledger-record')},'invoices':{'type':'array','items':ref('invoice')},'payments':{'type':'array','items':ref('payment')},'fx':{'type':'array','items':ref('fx-record')}})
write('episode',obj({'public':public,'truth':ref('truth'),'provenance':ref('provenance')}))
write('trajectory',obj({'episode_id':ID,'step':{'type':'integer','minimum':0,'maximum':100},'action':{'type':['object','null','array','string','number','boolean']},'observation':{'type':'object'},'reward':{'type':'number','minimum':-1,'maximum':1},'terminated':{'type':'boolean'},'truncated':{'type':'boolean'}}))
