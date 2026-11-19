"""Trusted ceiling check; never shipped in the policy image."""


def oracle_submission(truth):
    return {"episode_id": truth["episode_id"], "findings": [
        {"type": issue["type"], "affected_ids": issue["affected_ids"],
         "claimed_amount_minor": issue["expected_amount_minor"], "currency": issue["currency"],
         "evidence_ids": issue["evidence_sets"][0], "explanation": "Evaluator-only reference answer."}
        for issue in truth["issues"]
    ]}
