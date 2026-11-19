"""Consistent, semantics-preserving transformations used by paired checks."""
import copy
import random


def transform(episode, *, fields=(), tables=(), seed=113):
    out=copy.deepcopy(episode); rng=random.Random(seed); mapping={}
    # A single mapping is also applied to provenance, truth and namespaced references.
    allowed=set(fields)
    for table in ['ledger','invoices','payments']:
        for row in out['public'][table]:
            for key in allowed:
                value=row.get(key)
                if isinstance(value,str): mapping.setdefault(value,f'id_{rng.getrandbits(128):032x}')
    def walk(value):
        if isinstance(value,dict): return {k:walk(v) for k,v in value.items()}
        if isinstance(value,list): return [walk(v) for v in value]
        if isinstance(value,str):
            if value in mapping: return mapping[value]
            for prefix in ['ledger:','invoice:','payment:','doc:']:
                if value.startswith(prefix) and value[len(prefix):] in mapping: return prefix+mapping[value[len(prefix):]]
        return value
    out=walk(out)
    for table in tables: rng.shuffle(out['public'][table])
    return out
