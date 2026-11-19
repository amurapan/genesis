"""Integration-only sandbox probe; returns booleans, never file contents."""

import json
import os
from pathlib import Path
import socket


def main():
    checks = {"non_root": os.getuid() != 0,
              "no_docker_socket": not Path("/var/run/docker.sock").exists(),
              "no_host_workspace": not Path("/home/kudo/genesis").exists(),
              "no_fixtures": not Path("/app/fixtures").exists(),
              "no_evaluator_code": not Path("/app/src/sled/scoring_worker.py").exists(),
              "no_generator_code": not Path("/app/src/sled/generation.py").exists(),
              "no_episode_env": not any("seed" in k.lower() or "truth" in k.lower() for k in os.environ)}
    try:
        Path("/app/unauthorized-write").write_text("probe")
        checks["read_only_root"] = False
    except OSError:
        checks["read_only_root"] = True
    try:
        with socket.create_connection(("1.1.1.1", 443), timeout=0.5):
            checks["no_network"] = False
    except OSError:
        checks["no_network"] = True
    print(json.dumps(checks))


if __name__ == "__main__":
    main()
