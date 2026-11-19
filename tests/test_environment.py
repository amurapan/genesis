import os
import unittest

from sled.calculator import calculate
from sled.environment import AuditEnv
from sled.oracle import oracle_submission
from sled.protocol import ProtocolError, Wire, dumps, loads
from support import fixture


class EnvironmentTests(unittest.TestCase):
    def env(self, clean=False, **kwargs):
        env = AuditEnv(episode_factory=lambda s, c: fixture(clean), **kwargs)
        self.addCleanup(env.close)
        return env

    def test_reset_and_readonly_observations(self):
        env = self.env()
        initial, info = env.reset(19)
        self.assertEqual(initial["remaining_steps"], 100)
        self.assertRegex(initial["manifest"]["episode_id"], r"^ep_[0-9a-f]{32}$")
        self.assertFalse(any(k in dumps([initial, info]) for k in ("truth", "provenance", "seed", "expected_amount_minor")))
        initial["manifest"]["base_currency"] = "USD"
        action = {"action": "get_document", "doc_id": "invoice-doc-1"}
        result = env.step(action)
        result[0]["result"]["total_minor"] = 0
        self.assertEqual(env.trajectories[0]["observation"]["result"]["total_minor"], 100000)
        self.assertEqual(env.step(action)[0]["result"]["total_minor"], 100000)
        self.assertEqual(env.reset(19)[0]["manifest"]["base_currency"], "KZT")

    def test_all_tools_and_stable_cursor(self):
        env = self.env()
        env.reset(19)
        first = env.step({"action": "list_records", "table": "ledger", "limit": 2})[0]["result"]
        action = {"action": "list_records", "table": "ledger", "limit": 2, "cursor": first["next_cursor"]}
        self.assertEqual(env.step(action)[0]["result"], env.step(action)[0]["result"])
        for action in [{"action": "get_record", "table": "invoices", "id": "invoice-1"},
                       {"action": "get_record", "table": "policy", "id": "accounting"},
                       {"action": "get_document", "doc_id": "manifest:episode"}]:
            self.assertIn("result", env.step(action)[0])

    def test_errors_cost_steps_and_are_bounded(self):
        env = self.env()
        env.reset(0)
        for action in [None, {"action": "shell"}, {"action": "get_document", "doc_id": "../../truth.json"},
                       {"action": "list_records", "table": "ledger", "limit": 51},
                       {"action": "list_records", "table": []},
                       {"action": "get_record", "table": "ledger", "id": {}},
                       {"action": "calculator", "expression": "open('/private/truth.json')"}]:
            result = env.step(action)
            self.assertIn("error", result[0])
            self.assertEqual(result[1], 0)
            self.assertLess(len(dumps(result)), 300)
        self.assertEqual(env.steps, 7)
        self.assertEqual(env.inspection_steps, 7)

    def test_cursor_cannot_cross_table_or_episode(self):
        with AuditEnv() as env:
            env.reset(1)
            cursor = env.step({"action": "list_records", "table": "ledger", "limit": 1})[0]["result"]["next_cursor"]
            self.assertEqual(env.step({"action": "list_records", "table": "invoices", "cursor": cursor})[0]["error"]["code"], "INVALID_CURSOR")
            env.reset(2)
            self.assertEqual(env.step({"action": "list_records", "table": "ledger", "cursor": cursor})[0]["error"]["code"], "INVALID_CURSOR")

    def test_separate_evaluator_and_closed_reward(self):
        env = self.env(mode="evaluation")
        env.reset(0)
        self.assertNotEqual(env.evaluator.process.pid, os.getpid())
        result = env.step({"action": "submit", "findings": oracle_submission(fixture()["truth"])})
        self.assertEqual(result[1:], (0.0, True, False, {}))
        self.assertEqual(env.evaluation_result["reward"], 1)
        self.assertNotIn("tp", dumps(result))

    def test_invalid_submit_terminates_without_diagnostic_leak(self):
        for mode, reward in [("train", -1), ("evaluation", 0)]:
            env = self.env(mode=mode)
            env.reset(0)
            result = env.step({"action": "submit", "findings": {}})
            self.assertEqual(result[1], reward)
            self.assertTrue(result[2])
            self.assertFalse(env.evaluation_result["valid"])
            self.assertNotIn("submission_fields", dumps(result))

    def test_submit_on_step_100(self):
        env = self.env()
        env.reset(0)
        for _ in range(99):
            env.step({"action": "calculator", "expression": "1+1"})
        result = env.step({"action": "submit", "findings": oracle_submission(fixture()["truth"])})
        self.assertEqual(result[1:4], (.802, True, False))
        self.assertEqual(env.steps, 100)

    def test_100_inspections_truncates_to_empty(self):
        env = self.env(clean=True)
        env.reset(0)
        for _ in range(100):
            result = env.step({"action": "calculator", "expression": "1"})
        self.assertEqual(result[1:4], (.8, False, True))
        self.assertEqual(env.final_submission["findings"], [])

    def test_timeout_uses_empty_answer_formula(self):
        now = [0]
        env = self.env(clean=True, clock=lambda: now[0])
        env.reset(0)
        now[0] = 60
        result = env.step({"action": "calculator", "expression": "1"})
        self.assertEqual(result[1:4], (1, False, True))
        self.assertEqual(env.final_submission["findings"], [])

    def test_after_terminal_no_second_reward(self):
        env = self.env()
        env.reset(0)
        action = {"action": "submit", "findings": oracle_submission(fixture()["truth"])}
        env.step(action)
        self.assertEqual(env.step(action)[1], 0)
        self.assertEqual(env.steps, 1)
        self.assertEqual(len(env.trajectories), 1)

    def test_replayed_actions_have_identical_results(self):
        env = self.env()
        action = {"action": "list_records", "table": "ledger", "limit": 2}
        env.reset(0)
        first = [env.step(action), env.step({"action": "bad"})]
        env.reset(0)
        self.assertEqual(first, [env.step(action), env.step({"action": "bad"})])


class ArithmeticAndTransportTests(unittest.TestCase):
    def test_decimal_arithmetic(self):
        self.assertEqual(calculate("0.1 + 0.2"), "0.3")
        self.assertEqual(calculate("(60000-50000)/100"), "100")
        self.assertEqual(calculate("-(-2)*3"), "6")

    def test_calculator_rejects_code_and_resource_attacks(self):
        for value in ["", "1/0", "2**100", "__import__('os')", "(1).__class__", "1;2", "("*20+"1"+")"*20, "9"*129]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                calculate(value)

    def test_strict_json(self):
        for text in ['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', 'no json']:
            with self.subTest(text=text), self.assertRaises(ProtocolError):
                loads(text)

    def test_partial_json_line_cannot_bypass_deadline(self):
        read_fd, write_fd = os.pipe()
        with os.fdopen(read_fd, "rb") as reader, os.fdopen(write_fd, "wb") as writer:
            wire = Wire(reader, writer)
            os.write(write_fd, b'{"action":')
            with self.assertRaises(TimeoutError):
                wire.receive(timeout=.02)
