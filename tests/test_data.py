import copy
import unittest

from sled.generation import generate
from sled.validation import InvalidData, audit_public, verify_episode
from support import fixture, relabel


class DataTests(unittest.TestCase):
    def test_hand_calculated_episode(self):
        episode = fixture()
        results = audit_public(episode["public"])
        self.assertEqual({f["type"]: f["expected_amount_minor"] for f in results},
                         {"duplicate_invoice": 100000, "payment_allocation": 10000})
        self.assertEqual(sum(r["debit_minor"] for r in episode["public"]["ledger"]), 260000)
        self.assertTrue(verify_episode(episode)["valid"])

    def test_partial_payment_is_clean(self):
        clean = fixture(True)
        self.assertEqual(audit_public(clean["public"]), [])
        self.assertEqual(verify_episode(clean)["issue_count"], 0)
        self.assertEqual(sum(r["debit_minor"] for r in clean["public"]["ledger"]), 160000)

    def test_generator_sweep_and_repeat(self):
        for seed in range(20):
            for dup, alloc in [(0, 0), (1, 0), (0, 1), (1, 1), (3, 2)]:
                with self.subTest(seed=seed, duplicate=dup, allocation=alloc):
                    cfg = {"invoice_count": 10, "duplicate_count": dup, "allocation_count": alloc, 'fx_count':0, 'cutoff_count':0}
                    episode = generate(seed, cfg)
                    self.assertEqual(episode, generate(seed, cfg))
                    self.assertEqual(verify_episode(episode)["issue_count"], dup+alloc)

    def test_default_size_and_clean_repeated_amounts(self):
        episode = generate(19)
        self.assertGreaterEqual(len(episode["public"]["ledger"]), 200)
        clean = generate(19, {"duplicate_count": 0, "allocation_count": 0, 'fx_count':0, 'cutoff_count':0})
        amounts = [i["total_minor"] for i in clean["public"]["invoices"]]
        self.assertLess(len(set(amounts)), len(amounts))
        self.assertEqual(verify_episode(clean)["issue_count"], 0)

    def test_truth_amount_mutation_is_detected(self):
        episode = fixture()
        episode["truth"]["issues"][0]["expected_amount_minor"] += 1
        with self.assertRaises(InvalidData):
            verify_episode(episode)

    def test_missing_issue_is_detected(self):
        episode = fixture()
        episode["truth"]["issues"].pop()
        with self.assertRaises(InvalidData):
            verify_episode(episode)

    def test_missing_or_invented_evidence_is_detected(self):
        for proof in [["doc:invoice-doc-1"], ["private:answer"]]:
            episode = fixture()
            episode["truth"]["issues"][0]["evidence_sets"] = [proof]
            with self.subTest(proof=proof), self.assertRaises(InvalidData):
                verify_episode(episode)

    def test_balanced_data_mutation_is_detected(self):
        episode = fixture()
        for row in episode["public"]["ledger"]:
            if row["row_id"] == "r4":
                row["credit_minor"] -= 1
            if row["row_id"] == "r7":
                row["credit_minor"] += 1
        self.assertEqual(sum(r["debit_minor"]-r["credit_minor"] for r in episode["public"]["ledger"]), 0)
        with self.assertRaises(InvalidData):
            verify_episode(episode)

    def test_invalid_money_reference_and_date(self):
        for field, value in [("debit_minor", True), ("invoice_id", "unknown"), ("timestamp", "2026-11-01")]:
            episode = fixture()
            episode["public"]["ledger"][0][field] = value
            with self.subTest(field=field), self.assertRaises(InvalidData):
                verify_episode(episode)

    def test_provenance_replays_from_balanced_baseline(self):
        for episode in [fixture(), generate(51)]:
            baseline = episode["provenance"]["baseline_ledger"]
            self.assertEqual(sum(r["debit_minor"]-r["credit_minor"] for r in baseline), 0)
            restored = {r["row_id"]: copy.deepcopy(r) for r in baseline}
            for change in episode["provenance"]["modifications"]:
                rid = change["after"]["row_id"]
                self.assertEqual(restored.get(rid), change["before"])
                restored[rid] = change["after"]
            self.assertEqual(restored, {r["row_id"]: r for r in episode["public"]["ledger"]})

    def test_relabel_and_permute_preserves_independent_audit(self):
        episode = relabel(fixture())
        for table in ("ledger", "invoices", "payments"):
            episode["public"][table].reverse()
        self.assertEqual(verify_episode(episode)["issue_count"], 2)

    def test_config_fails_explicitly(self):
        for config in [{"invoice_count": True}, {"duplicate_count": -1}, {"allocation_count": 13}, {"fx_count": -1}, {'unknown':1}]:
            with self.subTest(config=config), self.assertRaises(ValueError):
                generate(19, config)
