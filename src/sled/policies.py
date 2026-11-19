"""Agent-side policies. They only consume observations, never truth or seeds."""

import random


def reconcile(data, episode_id, currency):
    rows = data["ledger"]
    invoices = {i["invoice_id"]: i for i in data["invoices"]}
    findings = []

    def finding(kind, ids, amount, evidence, explanation):
        findings.append({"type": kind, "affected_ids": sorted(ids),
                         "claimed_amount_minor": amount, "currency": currency,
                         "evidence_ids": sorted(set(evidence)), "explanation": explanation})

    for iid, invoice in invoices.items():
        booked = [r for r in rows if r["invoice_id"] == iid and r["payment_id"] is None
                  and r["account"] == "accounts_receivable"]
        excess = sum(r["debit_minor"] for r in booked) - invoice["total_minor"]
        if excess > 0:
            finding("duplicate_invoice", ["invoice:" + iid], excess,
                    ["doc:" + invoice["doc_id"], "policy:accounting"] + ["ledger:" + r["row_id"] for r in booked],
                    "Receivable recognition exceeds the source invoice total.")
    received = {iid: 0 for iid in invoices}
    previous_docs = {iid: [] for iid in invoices}
    for payment in sorted(data["payments"], key=lambda p: p["timestamp"]):
        if not payment["invoice_refs"] or len(payment["invoice_refs"]) != 1:
            continue
        iid = payment["invoice_refs"][0]
        invoice = invoices[iid]
        group = [r for r in rows if r["payment_id"] == payment["payment_id"]]
        applied = sum(r["credit_minor"] for r in group if r["account"] == "accounts_receivable")
        available = max(0, invoice["total_minor"] - received[iid])
        required = min(available, payment["amount_minor"])
        if applied < required:
            proof = ["doc:" + invoice["doc_id"], "doc:" + payment["doc_id"], "policy:accounting"]
            proof += ["ledger:" + r["row_id"] for r in group] + previous_docs[iid]
            if len(set(proof)) <= 10:
                finding("payment_allocation", ["invoice:" + iid, "payment:" + payment["payment_id"]],
                        required-applied, proof, "A receipt was allocated below the original invoice outstanding balance.")
        received[iid] += required
        previous_docs[iid].append("doc:" + payment["doc_id"])
    return {"episode_id": episode_id, "findings": findings[:30]}


class Scanner:
    def __init__(self, initial, flag_all=False):
        self.manifest = initial['manifest']
        self.profile = initial['policy_summary']['profile']
        self.episode_id = initial["manifest"]["episode_id"]
        self.currency = initial["manifest"]["base_currency"]
        self.data = {t: [] for t in ("ledger", "invoices", "payments")}
        if self.profile == 'receivables_v2': self.data['fx'] = []
        self.tables = list(self.data)
        self.index = 0
        self.cursor = None
        self.last = None
        self.flag_all = flag_all

    def action(self, observation):
        if observation["remaining_steps"] <= 1 or "error" in observation:
            return {"action": "submit", "findings": {"episode_id": self.episode_id, "findings": []}}
        if self.last == "scan":
            result = observation["result"]
            self.data[self.tables[self.index]].extend(result["records"])
            self.cursor = result["next_cursor"]
            if self.cursor is None:
                self.index += 1
        if self.index < len(self.tables):
            self.last = "scan"
            return {"action": "list_records", "table": self.tables[self.index], "cursor": self.cursor, "limit": 50}
        if self.last != "policy":
            self.last = "policy"
            return {"action": "get_document", "doc_id": "policy:accounting"}
        if self.flag_all:
            guesses = []
            for invoice in self.data["invoices"]:
                for kind in ("duplicate_invoice", "payment_allocation", "fx_conversion", "period_cutoff"):
                    guesses.append({"type": kind, "affected_ids": ["invoice:" + invoice["invoice_id"]],
                                    "claimed_amount_minor": invoice["total_minor"], "currency": self.currency,
                                    "evidence_ids": ["doc:" + invoice["doc_id"]], "explanation": "Flagged for review."})
            submission = {"episode_id": self.episode_id, "findings": guesses[:30]}
        else:
            if self.profile == 'receivables_v2':
                from .policy_v2 import reconcile as reconcile_v2
                submission = reconcile_v2(self.data, self.manifest, observation['result'])
            else:
                submission = reconcile(self.data, self.episode_id, self.currency)
        return {"action": "submit", "findings": submission}


class RandomExplorer:
    def __init__(self, initial):
        self.episode_id = initial["manifest"]["episode_id"]
        self.rng = random.Random(42)  # Policy seed, unrelated to the private episode seed.
        self.steps = 0

    def action(self, observation):
        if self.steps >= 12 or observation["remaining_steps"] <= 1:
            return {"action": "submit", "findings": {"episode_id": self.episode_id, "findings": []}}
        self.steps += 1
        return {"action": "list_records", "table": self.rng.choice(["ledger", "invoices", "payments"]), "limit": 1}
