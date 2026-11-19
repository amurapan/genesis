"""Versioned causal generator for the first, domestic-currency profile."""

import copy
import hashlib
import random

from .protocol import dumps

POLICY = {
    "profile": "domestic_receivables_v1",
    "supported_issue_types": ["duplicate_invoice", "payment_allocation"],
    "invoice_recognition": "Each source invoice is recognized exactly once",
    "allocation": "Allocate receipts up to the original invoice outstanding balance",
    "allocation_order": "Payment timestamps must be distinct within an invoice",
    "currency_scope": "Invoices and payments use the episode base currency",
    "rounding": "ROUND_HALF_EVEN",
    "amount_tolerance_minor": 0,
    "period_bounds": "start_inclusive_end_exclusive",
}


def generate(seed, config=None):
    if type(seed) is not int or not 0 <= seed < 2**64:
        raise ValueError("seed must be an unsigned 64-bit integer")
    config = {} if config is None else config
    if not isinstance(config, dict) or set(config) - {"invoice_count", "duplicate_count", "allocation_count"}:
        raise ValueError("Unsupported configuration")
    cfg = {"invoice_count": 50, "duplicate_count": 1, "allocation_count": 1} | config
    if any(type(v) is not int for v in cfg.values()):
        raise ValueError("Counts must be integers")
    n, dup, alloc = (cfg[k] for k in ("invoice_count", "duplicate_count", "allocation_count"))
    if not 1 <= n <= 100 or not 0 <= dup <= n or not 0 <= alloc <= n or dup + alloc > 12:
        raise ValueError("Invalid counts")

    def rng(label):
        material = dumps(["sled-generator-0.1.0", seed, cfg, label]).encode()
        return random.Random(int.from_bytes(hashlib.sha256(material).digest(), "big"))

    ids, world, corruption, order = (rng(k) for k in ("ids", "world", "corruption", "order"))

    def uid(prefix):
        return f"{prefix}_{ids.getrandbits(128):032x}"

    episode_id = uid("ep")
    ledger, invoices, payments, events = [], [], [], []

    def row(account, debit, credit, invoice, payment=None, timestamp=None):
        return {"row_id": uid("r"), "timestamp": timestamp or invoice["issued_at"],
                "account": account, "debit_minor": debit, "credit_minor": credit,
                "currency": "KZT", "entity_id": invoice["entity_id"],
                "invoice_id": invoice["invoice_id"], "payment_id": payment}

    for i in range(n):
        amount = world.randrange(100_000, 900_001)
        # Equal legitimate amounts prevent 'same amount means duplicate' shortcuts.
        if i > 0 and i % 5 == 0:
            amount = invoices[-1]["total_minor"]
        invoice = {"doc_id": uid("d"), "invoice_id": uid("i"), "entity_id": uid("e"),
                   "issued_at": f"2026-11-{1+i%9:02}T09:00:00+05:00",
                   "due_at": "2026-11-30T18:00:00+05:00", "currency": "KZT",
                   "total_minor": amount,
                   "line_items": [{"description": "Synthetic service", "quantity": 1,
                                   "unit_price_minor": amount, "total_minor": amount}]}
        paid = world.randrange(amount // 2, amount + 1)
        payment = {"doc_id": uid("d"), "payment_id": uid("p"),
                   "timestamp": f"2026-11-{12+i%9:02}T10:00:00+05:00",
                   "currency": "KZT", "amount_minor": paid,
                   "invoice_refs": [invoice["invoice_id"]]}
        debit = row("accounts_receivable", amount, 0, invoice)
        credit = row("revenue", 0, amount, invoice)
        cash = row("cash", paid, 0, invoice, payment["payment_id"], payment["timestamp"])
        applied = row("accounts_receivable", 0, paid, invoice, payment["payment_id"], payment["timestamp"])
        ledger.extend([debit, credit, cash, applied])
        invoices.append(invoice)
        payments.append(payment)
        events.append((invoice, payment, debit, credit, applied))

    baseline = copy.deepcopy(ledger)
    selected = list(range(n))
    corruption.shuffle(selected)
    modifications, injected = [], []
    for i in selected[:dup]:
        invoice, payment, debit, credit, applied = events[i]
        for original in (debit, credit):
            extra = copy.deepcopy(original)
            extra["row_id"] = uid("r")
            ledger.append(extra)
            modifications.append({"operation": "add", "table": "ledger", "before": None,
                                  "after": copy.deepcopy(extra), "cause": "duplicate_invoice"})
        injected.append(("duplicate_invoice", invoice, payment, invoice["total_minor"]))
    for i in selected[:alloc]:
        invoice, payment, debit, credit, applied = events[i]
        missing = corruption.randrange(1, payment["amount_minor"] // 2 + 1)
        before = copy.deepcopy(applied)
        applied["credit_minor"] -= missing
        clearing = row("unapplied_cash", 0, missing, invoice, payment["payment_id"], payment["timestamp"])
        ledger.append(clearing)
        modifications.extend([
            {"operation": "update", "table": "ledger", "before": before,
             "after": copy.deepcopy(applied), "cause": "payment_allocation"},
            {"operation": "add", "table": "ledger", "before": None,
             "after": copy.deepcopy(clearing), "cause": "payment_allocation"},
        ])
        injected.append(("payment_allocation", invoice, payment, missing))

    issues = []
    for kind, invoice, payment, amount in injected:
        affected = ["invoice:" + invoice["invoice_id"]]
        proof = ["doc:" + invoice["doc_id"], "policy:accounting"]
        if kind == "duplicate_invoice":
            proof += ["ledger:" + r["row_id"] for r in ledger
                      if r["invoice_id"] == invoice["invoice_id"] and r["payment_id"] is None
                      and r["account"] == "accounts_receivable"]
        else:
            affected.append("payment:" + payment["payment_id"])
            proof.append("doc:" + payment["doc_id"])
            proof += ["ledger:" + r["row_id"] for r in ledger if r["payment_id"] == payment["payment_id"]]
        issues.append({"issue_id": uid("issue"), "type": kind, "affected_ids": sorted(affected),
                       "expected_amount_minor": amount, "currency": "KZT",
                       "evidence_sets": [sorted(proof)]})
    for table in (ledger, invoices, payments):
        order.shuffle(table)
    public = {
        "manifest": {"schema_version": "1.0.0", "generator_version": "0.1.0",
                     "episode_id": episode_id, "base_currency": "KZT", "currency_exponents": {"KZT": 2},
                     "period_start": "2026-11-01T00:00:00+05:00", "period_end": "2026-12-01T00:00:00+05:00",
                     "timezone": "Asia/Almaty", "rounding": "ROUND_HALF_EVEN",
                     "record_counts": {"ledger": len(ledger), "invoices": n, "payments": n, "fx": 0},
                     "document_count": 2*n},
        "policy": copy.deepcopy(POLICY), "ledger": ledger, "invoices": invoices,
        "payments": payments, "fx": [],
    }
    return {"public": public,
            "truth": {"schema_version": "1.0.0", "episode_id": episode_id, "issues": issues},
            "provenance": {"generator_version": "0.1.0", "seed": seed, "config": cfg,
                           "baseline_ledger": baseline, "modifications": modifications}}
