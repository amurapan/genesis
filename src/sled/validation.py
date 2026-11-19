"""Independent public-data audit. Does not import generator, policies or matcher."""

from collections import Counter
import copy
from datetime import datetime


class InvalidData(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise InvalidData(message)


def timestamp(value):
    try:
        result = datetime.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        raise InvalidData("Invalid timestamp") from exc
    require(result.utcoffset() is not None, "Timestamp needs offset")
    return result


def audit_public(public):
    """Derive discrepancies before any access to truth."""
    if public['policy']['profile'] == 'receivables_v2':
        from .validation_v2 import audit
        return audit(public)
    manifest, policy = public["manifest"], public["policy"]
    require(policy["profile"] == "domestic_receivables_v1", "Unsupported accounting profile")
    require(type(policy["amount_tolerance_minor"]) is int and policy["amount_tolerance_minor"] == 0, "Profile requires exact amounts")
    require(isinstance(manifest["episode_id"], str) and bool(manifest["episode_id"]), "Invalid episode ID")
    base = manifest["base_currency"]
    start, end = timestamp(manifest["period_start"]), timestamp(manifest["period_end"])
    require(start < end, "Invalid period")
    require(type(manifest["currency_exponents"][base]) is int and 0 <= manifest["currency_exponents"][base] <= 9, "Invalid currency exponent")
    require(public["fx"] == [], "FX not implemented in this profile")
    for table in ("ledger", "invoices", "payments", "fx"):
        require(type(manifest["record_counts"][table]) is int and len(public[table]) == manifest["record_counts"][table], "Manifest count mismatch")
    require(type(manifest["document_count"]) is int and manifest["document_count"] == len(public["invoices"]) + len(public["payments"]), "Document count mismatch")
    invoices = {i["invoice_id"]: i for i in public["invoices"]}
    payments = {p["payment_id"]: p for p in public["payments"]}
    require(len(invoices) == len(public["invoices"]), "Duplicate invoice identity")
    require(len(payments) == len(public["payments"]), "Duplicate payment identity")
    doc_ids = [d["doc_id"] for d in public["invoices"] + public["payments"]]
    require(len(doc_ids) == len(set(doc_ids)), "Duplicate document identity")
    rows = public["ledger"]
    require(len({r["row_id"] for r in rows}) == len(rows), "Duplicate row identity")
    for r in rows:
        require(r["currency"] == base, "Unsupported ledger currency")
        require(r["invoice_id"] in invoices, "Missing invoice reference")
        require(r["payment_id"] is None or r["payment_id"] in payments, "Missing payment reference")
        require(r["entity_id"] == invoices[r["invoice_id"]]["entity_id"], "Wrong entity")
        require(r["account"] in {"cash", "accounts_receivable", "revenue", "unapplied_cash"}, "Unknown account")
        require(type(r["debit_minor"]) is int and type(r["credit_minor"]) is int, "Non-integer money")
        require(r["debit_minor"] >= 0 and r["credit_minor"] >= 0 and bool(r["debit_minor"]) != bool(r["credit_minor"]), "Invalid debit/credit")
        require(start <= timestamp(r["timestamp"]) < end, "Unsupported period discrepancy")
    require(sum(r["debit_minor"] - r["credit_minor"] for r in rows) == 0, "Ledger is unbalanced")
    findings = []

    def found(kind, affected, amount, evidence):
        require(0 < len(set(evidence)) <= 10, "Evidence exceeds budget")
        findings.append({"type": kind, "affected_ids": sorted(affected),
                         "expected_amount_minor": amount, "currency": base,
                         "required_evidence": sorted(set(evidence))})

    for iid, invoice in invoices.items():
        require(invoice["currency"] == base, "Foreign invoice not supported")
        require(type(invoice["total_minor"]) is int and invoice["total_minor"] > 0, "Invalid invoice amount")
        require(start <= timestamp(invoice["issued_at"]) < end, "Invoice outside profile period")
        require(timestamp(invoice["due_at"]) >= timestamp(invoice["issued_at"]), "Invalid due date")
        require(bool(invoice["line_items"]), "Missing line items")
        for item in invoice["line_items"]:
            require(all(type(item[k]) is int for k in ("quantity", "unit_price_minor", "total_minor")), "Invalid item money")
            require(item["quantity"] > 0 and item["unit_price_minor"] > 0, "Invalid line item")
            require(item["quantity"] * item["unit_price_minor"] == item["total_minor"], "Line total mismatch")
        require(sum(x["total_minor"] for x in invoice["line_items"]) == invoice["total_minor"], "Invoice total mismatch")
        group = [r for r in rows if r["invoice_id"] == iid and r["payment_id"] is None]
        require(all(r["timestamp"] == invoice["issued_at"] for r in group), "Invoice date mismatch")
        ar = [r for r in group if r["account"] == "accounts_receivable"]
        revenue = [r for r in group if r["account"] == "revenue"]
        require(len(group) == len(ar) + len(revenue), "Unexpected invoice account")
        require(all(r["credit_minor"] == 0 for r in ar) and all(r["debit_minor"] == 0 for r in revenue), "Invoice direction")
        booked = sum(r["debit_minor"] for r in ar)
        require(booked == sum(r["credit_minor"] for r in revenue), "Invoice journal unbalanced")
        require(booked >= invoice["total_minor"] and all(r["debit_minor"] == invoice["total_minor"] for r in ar), "Unmodeled invoice discrepancy")
        if booked > invoice["total_minor"]:
            found("duplicate_invoice", ["invoice:" + iid], booked - invoice["total_minor"],
                  ["doc:" + invoice["doc_id"], "policy:accounting"] + ["ledger:" + r["row_id"] for r in ar])

    outstanding = {iid: i["total_minor"] for iid, i in invoices.items()}
    previous = set()
    earlier = {iid: [] for iid in invoices}
    for payment in sorted(payments.values(), key=lambda p: timestamp(p["timestamp"])):
        require(payment["currency"] == base, "Foreign payment not supported yet")
        require(type(payment["amount_minor"]) is int and payment["amount_minor"] > 0, "Refunds not implemented yet")
        require(isinstance(payment["invoice_refs"], list) and len(payment["invoice_refs"]) == 1, "Expected one explicit invoice reference")
        iid = payment["invoice_refs"][0]
        require(iid in invoices, "Unknown payment invoice")
        time = timestamp(payment["timestamp"])
        require(time >= timestamp(invoices[iid]["issued_at"]) and start <= time < end, "Invalid payment date")
        require((iid, time) not in previous, "Ambiguous simultaneous allocation")
        previous.add((iid, time))
        group = [r for r in rows if r["payment_id"] == payment["payment_id"]]
        require(all(r["invoice_id"] == iid and timestamp(r["timestamp"]) == time for r in group), "Payment linkage mismatch")
        cash = [r for r in group if r["account"] == "cash"]
        ar = [r for r in group if r["account"] == "accounts_receivable"]
        clearing = [r for r in group if r["account"] == "unapplied_cash"]
        require(len(group) == len(cash) + len(ar) + len(clearing), "Unexpected payment account")
        require(all(r["credit_minor"] == 0 for r in cash) and all(r["debit_minor"] == 0 for r in ar + clearing), "Payment direction")
        require(sum(r["debit_minor"] for r in cash) == payment["amount_minor"], "Cash receipt mismatch")
        applied = sum(r["credit_minor"] for r in ar)
        require(applied + sum(r["credit_minor"] for r in clearing) == payment["amount_minor"], "Payment journal unbalanced")
        expected = min(outstanding[iid], payment["amount_minor"])
        require(applied <= expected, "Over-allocation outside profile")
        if applied < expected:
            proof = ["policy:accounting", "doc:" + invoices[iid]["doc_id"], "doc:" + payment["doc_id"]]
            proof += ["ledger:" + r["row_id"] for r in group] + earlier[iid]
            found("payment_allocation", ["invoice:" + iid, "payment:" + payment["payment_id"]], expected - applied, proof)
        outstanding[iid] -= expected
        earlier[iid].append("doc:" + payment["doc_id"])
    return findings


def verify_episode(episode):
    """Independent derivation first, then comparison to the private answer key."""
    derived = audit_public(episode["public"])
    truth = episode["truth"]
    require(truth["episode_id"] == episode["public"]["manifest"]["episode_id"], "Truth belongs to another episode")
    require(len(truth["issues"]) <= 12, "Too many issues")
    require(len({i["issue_id"] for i in truth["issues"]}) == len(truth["issues"]), "Duplicate issue ID")
    if episode['public']['policy']['profile']=='receivables_v2':
        cfg=episode['provenance']['config']
        requested={kind:cfg[key] for kind,key in [('duplicate_invoice','duplicate_count'),('payment_allocation','allocation_count'),('fx_conversion','fx_count'),('period_cutoff','cutoff_count')]}
        actual=Counter(x['type'] for x in truth['issues'])
        require(all(actual[k]==v for k,v in requested.items()), 'Requested error counts not implemented')

    def signature(issue):
        return (issue["type"], tuple(sorted(set(issue["affected_ids"]))), issue["expected_amount_minor"], issue["currency"])

    require(Counter(signature(x) for x in derived) == Counter(signature(x) for x in truth["issues"]), "Truth differs from independent public audit")
    known = {"policy:accounting", "manifest:episode"}
    known.update("ledger:" + r["row_id"] for r in episode["public"]["ledger"])
    known.update("doc:" + d["doc_id"] for d in episode["public"]["invoices"] + episode["public"]["payments"])
    known.update('fx:'+r['date']+':'+r['source_currency']+':'+r['target_currency'] for r in episode['public']['fx'])
    expected = {signature(x): set(x["required_evidence"]) for x in derived}
    for issue in truth["issues"]:
        require(type(issue["expected_amount_minor"]) is int and issue["expected_amount_minor"] > 0, "Invalid truth money")
        require(bool(issue["evidence_sets"]), "Missing evidence")
        for proof in issue["evidence_sets"]:
            require(0 < len(proof) <= 10 and set(proof) <= known, "Unavailable evidence")
            required = expected[signature(issue)]
            if issue['type'] == 'period_cutoff' and issue['affected_ids'][0].startswith('invoice:'):
                # Any same-date AR row is an equivalent period witness, independent of ID/order.
                iid = issue['affected_ids'][0].split(':',1)[1]
                witnesses = {'ledger:'+r['row_id'] for r in episode['public']['ledger'] if r['invoice_id']==iid and r['payment_id'] is None and r['account']=='accounts_receivable'}
                require((required-witnesses)<=set(proof) and bool(set(proof)&witnesses), 'Insufficient period evidence')
            else:
                require(required <= set(proof), "Insufficient evidence")
    provenance = episode['provenance']
    baseline = copy.deepcopy(episode['public'])
    baseline['ledger'] = copy.deepcopy(provenance['baseline_ledger'])
    baseline['manifest']['record_counts']['ledger'] = len(baseline['ledger'])
    require(not audit_public(baseline), 'Baseline contains discrepancies')
    replay = {r['row_id']: r for r in baseline['ledger']}
    for change in provenance['modifications']:
        require(change['table']=='ledger' and change['operation'] in ('add','update','delete'), 'Invalid causal change')
        before, after = change['before'], change['after']
        rid = (after or before)['row_id']
        require(replay.get(rid)==before, 'Provenance before state mismatch')
        if after is None: del replay[rid]
        else: replay[rid] = copy.deepcopy(after)
    require(replay=={r['row_id']:r for r in episode['public']['ledger']}, 'Provenance does not reproduce final ledger')
    return {"valid": True, "issue_count": len(derived), "findings": derived, 'baseline_valid':True, 'provenance_valid':True}
