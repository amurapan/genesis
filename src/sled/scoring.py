"""Public, deterministic matching and reward rules."""

from fractions import Fraction

TYPES = {"duplicate_invoice", "payment_allocation", "fx_conversion", "period_cutoff"}
FIELDS = {"type", "affected_ids", "claimed_amount_minor", "currency",
          "evidence_ids", "explanation"}


def submission_error(submission, episode_id):
    if not isinstance(submission, dict) or set(submission) != {"episode_id", "findings"}:
        return "submission_fields"
    if submission["episode_id"] != episode_id:
        return "episode_id"
    findings = submission["findings"]
    if not isinstance(findings, list) or len(findings) > 30:
        return "findings_limit"
    for finding in findings:
        if not isinstance(finding, dict) or set(finding) != FIELDS:
            return "finding_fields"
        if not isinstance(finding["type"], str) or not isinstance(finding["currency"], str):
            return "finding_types"
        if type(finding["claimed_amount_minor"]) is not int:
            return "amount_type"
        for field in ("affected_ids", "evidence_ids"):
            values = finding[field]
            if not isinstance(values, list) or any(not isinstance(x, str) or not x for x in values):
                return "id_type"
        if len(finding["evidence_ids"]) > 10:
            return "evidence_limit"
        explanation = finding["explanation"]
        if not isinstance(explanation, str) or len(explanation) > 1000:
            return "explanation_limit"
    return None


def score(submission, truth, public_evidence_ids, inspection_steps, tolerance=0):
    if type(inspection_steps) is not int or not 0 <= inspection_steps <= 100:
        raise ValueError("Invalid inspection count")
    if type(tolerance) is not int or tolerance < 0:
        raise ValueError("Invalid tolerance")
    error = submission_error(submission, truth["episode_id"])
    if error:
        return {"valid": False, "error": error, "reward": -1.0,
                "tp": 0, "fp": 0, "fn": len(truth["issues"]),
                "precision": 0.0, "recall": 0.0, "f1": 0.0,
                "inspection_steps": inspection_steps, "matches": []}
    findings, issues = submission["findings"], truth["issues"]
    known = set(public_evidence_ids)
    edges = []
    for finding in findings:
        evidence = set(finding["evidence_ids"])
        candidates = []
        for index, issue in enumerate(issues):
            if (finding["type"] == issue["type"]
                    and set(finding["affected_ids"]) == set(issue["affected_ids"])
                    and finding["currency"] == issue["currency"]
                    and abs(finding["claimed_amount_minor"] - issue["expected_amount_minor"]) <= tolerance
                    and evidence <= known
                    and any(set(proof) <= evidence for proof in issue["evidence_sets"])):
                candidates.append(index)
        edges.append(sorted(candidates, key=lambda i: issues[i]["issue_id"]))

    # Augmenting paths give maximum cardinality; a greedy matcher can lose TPs.
    owner = {}

    def augment(finding_index, visited):
        for issue_index in edges[finding_index]:
            if issue_index in visited:
                continue
            visited.add(issue_index)
            if issue_index not in owner or augment(owner[issue_index], visited):
                owner[issue_index] = finding_index
                return True
        return False

    for index in range(len(findings)):
        augment(index, set())
    tp = len(owner)
    fp, fn = len(findings) - tp, len(issues) - tp
    precision = Fraction(tp, tp + fp) if tp + fp else Fraction(0)
    recall = Fraction(tp, tp + fn) if tp + fn else Fraction(0)
    f1 = Fraction(2 * tp, 2 * tp + fp + fn) if 2 * tp + fp + fn else Fraction(1)
    reward = max(Fraction(-1), min(Fraction(1), 2 * f1 - 1 - Fraction(inspection_steps, 500)))
    return {"valid": True, "error": None, "tp": tp, "fp": fp, "fn": fn,
            "precision": float(precision), "recall": float(recall), "f1": float(f1),
            "reward": float(reward), "inspection_steps": inspection_steps,
            "matches": [{"finding_index": fi, "issue_id": issues[ii]["issue_id"]}
                        for ii, fi in sorted(owner.items())]}
