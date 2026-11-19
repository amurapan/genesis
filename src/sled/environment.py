"""Trusted environment and read-only tool broker."""

import copy
import hashlib
import hmac
import re
import subprocess
import sys
import time

from .calculator import calculate
from .generation import generate
from .protocol import Wire, dumps


class ToolError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message


class PublicStore:
    def __init__(self, public):
        self.public = copy.deepcopy(public)
        self.tables = {t: self.public[t] for t in ("ledger", "invoices", "payments", "fx")}
        self.tables["policy"] = [self.public["policy"]]
        self.indices = {}
        fields = {"ledger": "row_id", "invoices": "invoice_id", "payments": "payment_id"}
        for table, field in fields.items():
            self.indices[table] = {r[field]: r for r in self.tables[table]}
        self.indices["fx"] = {f"{r['date']}:{r['source_currency']}:{r['target_currency']}": r for r in self.tables["fx"]}
        self.indices["policy"] = {"accounting": self.public["policy"]}
        self.documents = {d["doc_id"]: d for d in self.public["invoices"] + self.public["payments"]}
        self.documents.update({"policy:accounting": self.public["policy"], "manifest:episode": self.public["manifest"]})
        self.key = hashlib.sha256(dumps(self.public).encode()).digest()

    def evidence_ids(self):
        return (["ledger:" + r["row_id"] for r in self.public["ledger"]]
                + ["doc:" + d["doc_id"] for d in self.public["invoices"] + self.public["payments"]]
                + ["fx:" + key for key in self.indices["fx"]]
                + ["policy:accounting", "manifest:episode"])

    def _cursor(self, table, offset):
        signature = hmac.new(self.key, f"{table}:{offset}".encode(), hashlib.sha256).hexdigest()[:24]
        return f"{offset}.{signature}"

    def list_records(self, table, cursor=None, limit=50):
        if not isinstance(table, str) or table not in self.tables:
            raise ToolError("UNKNOWN_TABLE", "Unknown table")
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ToolError("INVALID_LIMIT", "Limit must be an integer from 1 to 50")
        offset = 0
        if cursor is not None:
            if not isinstance(cursor, str) or not re.fullmatch(r"\d{1,8}\.[0-9a-f]{24}", cursor):
                raise ToolError("INVALID_CURSOR", "Invalid cursor")
            offset = int(cursor.split(".")[0])
            if not hmac.compare_digest(cursor, self._cursor(table, offset)) or not 0 < offset < len(self.tables[table]):
                raise ToolError("INVALID_CURSOR", "Invalid cursor")
        records = self.tables[table][offset:offset + limit]
        next_offset = offset + len(records)
        return {"records": records, "next_cursor": self._cursor(table, next_offset) if next_offset < len(self.tables[table]) else None}

    def get_record(self, table, id):
        if not isinstance(table, str) or table not in self.indices:
            raise ToolError("UNKNOWN_TABLE", "Unknown table")
        if not isinstance(id, str) or id not in self.indices[table]:
            raise ToolError("UNKNOWN_RECORD", "Record not found")
        return self.indices[table][id]

    def get_document(self, doc_id):
        if not isinstance(doc_id, str) or doc_id not in self.documents:
            raise ToolError("UNKNOWN_DOCUMENT", "Document not found")
        return self.documents[doc_id]


class EvaluatorClient:
    def __init__(self, truth, evidence_ids, tolerance):
        self.process = subprocess.Popen([sys.executable, "-m", "sled.scoring_worker"],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.wire = Wire(self.process.stdout, self.process.stdin)
        try:
            self.wire.send({"op": "load", "truth": truth, "evidence_ids": evidence_ids, "tolerance": tolerance})
            if self.wire.receive() != {"ready": True}:
                raise RuntimeError("Evaluator did not initialize")
        except BaseException:
            self.close()
            raise

    def evaluate(self, submission, steps):
        self.wire.send({"op": "score", "submission": submission, "inspection_steps": steps})
        return self.wire.receive()

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        self.process.stdin.close()
        self.process.stdout.close()


class AuditEnv:
    """reset is called by the trusted harness, never by the agent process."""

    def __init__(self, mode="train", episode_factory=generate, timeout_seconds=60, clock=time.monotonic):
        if mode not in ("train", "evaluation"):
            raise ValueError("Invalid mode")
        if not 0 < timeout_seconds <= 60:
            raise ValueError("Timeout must be in (0, 60]")
        self.mode, self.factory, self.timeout_seconds, self.clock = mode, episode_factory, timeout_seconds, clock
        self.evaluator = None
        self.store = None

    def reset(self, seed, config=None):
        self.close()
        self.store = None
        episode = self.factory(seed, config)
        store = PublicStore(episode["public"])
        evaluator = EvaluatorClient(episode["truth"], store.evidence_ids(), store.public["policy"]["amount_tolerance_minor"])
        self.store, self.evaluator = store, evaluator
        self.steps = self.inspection_steps = 0
        self.terminated = self.truncated = False
        self.evaluation_result = self.final_submission = None
        self.trajectories = []
        self.deadline = self.clock() + self.timeout_seconds
        policy = store.public["policy"]
        observation = {"task": "Find accounting discrepancies and submit findings with public evidence.",
                       "manifest": store.public["manifest"],
                       "policy_summary": {k: policy[k] for k in ("profile", "supported_issue_types", "currency_scope", "amount_tolerance_minor")},
                       "remaining_steps": 100}
        return copy.deepcopy(observation), {"schema_version": "1.0.0"}

    def _empty(self):
        return {"episode_id": self.store.public["manifest"]["episode_id"], "findings": []}

    def _finish(self, submission, truncated=False):
        self.final_submission = copy.deepcopy(submission)
        self.evaluation_result = self.evaluator.evaluate(submission, self.inspection_steps)
        self.terminated, self.truncated = not truncated, truncated
        return self.evaluation_result["reward"] if self.mode == "train" else 0.0

    def _record(self, action, observation, reward):
        result = (copy.deepcopy(observation), reward, self.terminated, self.truncated, {})
        self.trajectories.append({"episode_id": self.store.public["manifest"]["episode_id"],
                                  "step": self.steps, "action": copy.deepcopy(action),
                                  "observation": copy.deepcopy(result[0]), "reward": reward,
                                  "terminated": self.terminated, "truncated": self.truncated})
        return result

    def truncate(self, reason="TIME_LIMIT"):
        if self.terminated or self.truncated:
            return self.step(None)
        reward = self._finish(self._empty(), truncated=True)
        observation = {"error": {"code": reason, "message": "Episode interrupted"}, "remaining_steps": 100-self.steps}
        return self._record(None, observation, reward)

    def step(self, action):
        if self.store is None:
            raise RuntimeError("Call reset first")
        if self.terminated or self.truncated:
            return ({"error": {"code": "EPISODE_DONE", "message": "Reset required"},
                     "remaining_steps": 100-self.steps}, 0.0, self.terminated, self.truncated, {})
        if self.clock() >= self.deadline:
            return self.truncate()
        self.steps += 1
        reward = 0.0
        name = action.get("action") if isinstance(action, dict) else None
        try:
            dumps(action)
        except (TypeError, ValueError, RecursionError):
            action, name = None, None
        if name == "submit":
            submission = action.get("findings") if set(action) == {"action", "findings"} else None
            reward = self._finish(submission)
            observation = {"result": {"submitted": True}, "remaining_steps": 100-self.steps}
        else:
            self.inspection_steps += 1
            try:
                if not isinstance(action, dict) or not isinstance(name, str):
                    raise ToolError("INVALID_ACTION", "Expected an action object")
                kwargs = {k: v for k, v in action.items() if k != "action"}
                if name == "calculator":
                    if set(kwargs) != {"expression"}:
                        raise ToolError("INVALID_ACTION", "Invalid arguments")
                    try:
                        result = {"value": calculate(kwargs["expression"])}
                    except ValueError:
                        raise ToolError("INVALID_EXPRESSION", "Invalid arithmetic expression") from None
                elif name in ("list_records", "get_record", "get_document"):
                    try:
                        result = getattr(self.store, name)(**kwargs)
                    except TypeError:
                        raise ToolError("INVALID_ACTION", "Invalid arguments") from None
                else:
                    raise ToolError("UNKNOWN_ACTION", "Unknown action")
                observation = {"result": result, "remaining_steps": 100-self.steps}
            except ToolError as exc:
                observation = {"error": {"code": exc.code, "message": exc.message}, "remaining_steps": 100-self.steps}
            if self.clock() >= self.deadline:
                reward = self._finish(self._empty(), truncated=True)
                observation = {"error": {"code": "TIME_LIMIT", "message": "Episode interrupted"}, "remaining_steps": 100-self.steps}
            elif self.steps == 100:
                reward = self._finish(self._empty(), truncated=True)
        return self._record(action, observation, reward)

    def close(self):
        if self.evaluator is not None:
            self.evaluator.close()
            self.evaluator = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
