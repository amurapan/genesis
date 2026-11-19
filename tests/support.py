import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fixture(clean=False):
    return json.loads((ROOT / "fixtures" / ("manual_clean.json" if clean else "manual_errors.json")).read_text())


def relabel(episode):
    public = episode["public"]
    ids = []
    for table, fields in (("ledger", ("row_id",)), ("invoices", ("invoice_id", "doc_id", "entity_id")),
                         ("payments", ("payment_id", "doc_id"))):
        for row in public[table]:
            ids.extend(row[k] for k in fields)
    mapping = {old: f"renamed-{len(ids)-i:04}" for i, old in enumerate(dict.fromkeys(ids))}

    def walk(value):
        if isinstance(value, dict):
            return {k: walk(v) for k, v in value.items()}
        if isinstance(value, list):
            return [walk(v) for v in value]
        if isinstance(value, str):
            if value in mapping:
                return mapping[value]
            for prefix in ("ledger:", "invoice:", "payment:", "doc:"):
                if value.startswith(prefix) and value[len(prefix):] in mapping:
                    return prefix + mapping[value[len(prefix):]]
        return value
    return walk(copy.deepcopy(episode))
