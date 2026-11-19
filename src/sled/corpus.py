"""Fixed scenario families for acceptance and disjoint public train/dev sets."""
from .generation import generate

CLEAN={'duplicate_count':0,'allocation_count':0,'fx_count':0,'cutoff_count':0}
PLAIN=CLEAN|{'foreign_payments':False,'split_count':0,'refund_count':0,'null_count':0}
DATA_CONFIGS=[
 PLAIN,
 PLAIN|{'invoice_count':12},
 PLAIN|{'split_count':4},
 PLAIN|{'invoice_count':20},
 CLEAN|{'split_count':3,'refund_count':3,'null_count':2},
 PLAIN|{'duplicate_count':1},
 PLAIN|{'duplicate_count':4},
 PLAIN|{'allocation_count':1,'allocation_mode':'missing'},
 PLAIN|{'allocation_count':2},
 CLEAN|{'fx_count':1,'fx_mode':'rate'},
 CLEAN|{'fx_count':1,'fx_mode':'date'},
 CLEAN|{'cutoff_count':1,'cutoff_direction':'early'},
 CLEAN|{'cutoff_count':1,'cutoff_direction':'late','cutoff_target':'invoice'},
 {'interaction':False},
 {'interaction':False,'invoice_count':90,'ledger_rows':2000,'split_count':4,'refund_count':4,'null_count':2},
 CLEAN|{'fx_count':1,'cutoff_count':1},
 PLAIN|{'duplicate_count':1,'allocation_count':1},
 CLEAN|{'fx_count':1,'cutoff_count':1,'split_count':8},
 CLEAN|{'duplicate_count':1,'allocation_count':1,'refund_count':4},
 {'base_currency':'KWD','period_start':'2026-12-01T00:00:00-07:00','rounding':'ROUND_HALF_UP','fx_mode':'date'},
]


def holdout(seed_base=710000):
    return [generate(seed_base+i,c) for i,c in enumerate(DATA_CONFIGS)]


def public_split(name):
    if name not in ('train','dev'): raise ValueError('Unknown split')
    # Different configuration halves and independently chosen seeds.
    indices=[0,2,4,5,7,9,11,13,15,17] if name=='train' else [1,3,6,8,10,12,14,16,18,19]
    base=11000 if name=='train' else 39000
    return [(base+i,DATA_CONFIGS[index],generate(base+i,DATA_CONFIGS[index])) for i,index in enumerate(indices)]
