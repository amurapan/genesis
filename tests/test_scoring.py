import copy
import unittest

from sled.environment import PublicStore
from sled.oracle import oracle_submission
from sled.scoring import score
from support import fixture, relabel

MISSING = object()


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.episode = fixture()
        self.answer = oracle_submission(self.episode["truth"])

    def grade(self, answer=MISSING, steps=0, episode=None):
        e = episode or self.episode
        return score(self.answer if answer is MISSING else answer, e["truth"], PublicStore(e["public"]).evidence_ids(), steps)

    def test_perfect_and_empty(self):
        good = self.grade(steps=4)
        empty = self.grade({"episode_id": self.answer["episode_id"], "findings": []})
        self.assertEqual((good["tp"], good["fp"], good["fn"]), (2, 0, 0))
        self.assertEqual(good["reward"], 0.992)
        self.assertEqual(empty["reward"], -1)

    def test_clean_metrics_and_false_accusation(self):
        episode = fixture(True)
        empty = oracle_submission(episode["truth"])
        result = self.grade(empty, episode=episode)
        self.assertEqual((result["precision"], result["recall"], result["f1"], result["reward"]), (0, 0, 1, 1))
        bad = copy.deepcopy(self.answer)
        bad["episode_id"] = empty["episode_id"]
        self.assertEqual(self.grade(bad, episode=episode)["reward"], -1)

    def test_duplicate_findings_are_false_positives(self):
        self.answer["findings"] = [self.answer["findings"][0]] * 10
        result = self.grade()
        self.assertEqual((result["tp"], result["fp"], result["fn"]), (1, 9, 1))
        self.assertAlmostEqual(result["f1"], 1/6)
        self.assertAlmostEqual(result["reward"], -2/3)

    def test_semantic_mismatches_are_false_positives(self):
        mutations = [("type", "period_cutoff"), ("affected_ids", ["invoice:wrong"]),
                     ("claimed_amount_minor", 99999), ("currency", "USD"),
                     ("evidence_ids", []), ("evidence_ids", ["doc:invoice-doc-1"]),
                     ("evidence_ids", ["private:answer"])]
        for field, value in mutations:
            answer = copy.deepcopy(self.answer)
            answer["findings"][0][field] = value
            with self.subTest(field=field, value=value):
                result = self.grade(answer)
                self.assertEqual((result["tp"], result["fp"], result["fn"]), (1, 1, 1))

    def test_maximum_matching_not_greedy(self):
        first = copy.deepcopy(self.episode["truth"]["issues"][0])
        first.update(issue_id="a", expected_amount_minor=100)
        second = dict(first, issue_id="b", expected_amount_minor=102)
        truth = {"episode_id": "match", "issues": [first, second]}
        answer = oracle_submission(truth)
        answer["findings"][0]["claimed_amount_minor"] = 101
        answer["findings"][1]["claimed_amount_minor"] = 100
        result = score(answer, truth, PublicStore(self.episode["public"]).evidence_ids(), 0, tolerance=1)
        self.assertEqual(result["tp"], 2)

    def test_invalid_structure_and_boundaries(self):
        bad_cases = [None, {}, dict(self.answer, episode_id="other")]
        for field, value in [("claimed_amount_minor", True), ("evidence_ids", ["x"]*11), ("explanation", "я"*1001)]:
            answer = copy.deepcopy(self.answer)
            answer["findings"][0][field] = value
            bad_cases.append(answer)
        bad_cases.append(dict(self.answer, findings=[self.answer["findings"][0]]*31))
        for answer in bad_cases:
            with self.subTest(answer=answer):
                result = self.grade(answer)
                self.assertFalse(result["valid"])
                self.assertEqual(result["reward"], -1)
        self.answer["findings"][0]["explanation"] = "я"*1000
        self.assertTrue(self.grade()["valid"])

    def test_explanation_order_and_duplicate_ids_do_not_improve_score(self):
        expected = self.grade()
        self.answer["findings"].reverse()
        for finding in self.answer["findings"]:
            finding["explanation"] = ""
            finding["affected_ids"] *= 2
            finding["evidence_ids"].reverse()
        result = self.grade()
        self.assertEqual(result["reward"], expected["reward"])
        self.assertEqual(result["tp"], 2)

    def test_inspection_cost_and_clipping(self):
        self.assertAlmostEqual(self.grade(steps=40)["reward"] - self.grade(steps=41)["reward"], .002)
        self.assertEqual(self.grade(steps=99)["reward"], .802)
        empty = {"episode_id": self.answer["episode_id"], "findings": []}
        self.assertEqual(self.grade(empty, steps=100)["reward"], -1)

    def test_relabeling_preserves_score(self):
        episode = relabel(self.episode)
        result = self.grade(oracle_submission(episode["truth"]), episode=episode)
        self.assertEqual(result["reward"], 1)
