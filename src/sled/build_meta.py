"""Fingerprint the exact inputs copied into the agent image."""

import hashlib
from pathlib import Path


def agent_source_hash():
    root = Path(__file__).resolve().parents[2]
    names = ["containers/agent.Dockerfile"] + ["src/sled/" + name for name in
             ("__init__.py", "agent.py", "policies.py", "policy_v2.py", "protocol.py", "probe.py")]
    digest = hashlib.sha256()
    for name in sorted(names):
        digest.update(name.encode() + b"\0")
        digest.update((root / name).read_bytes() + b"\0")
    return digest.hexdigest()


if __name__ == "__main__":
    print(agent_source_hash())
