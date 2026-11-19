"""Minimal observation/action client installed in the agent image."""

import argparse
import sys

from .policies import RandomExplorer, Scanner
from .protocol import dumps, loads


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", choices=["reconciler", "random", "flag_all"], default="reconciler")
    args = parser.parse_args()
    policy = None
    for line in sys.stdin.buffer:
        message = loads(line)
        if message["terminated"] or message["truncated"]:
            break
        observation = message["observation"]
        if policy is None:
            policy = RandomExplorer(observation) if args.policy == "random" else Scanner(observation, args.policy == "flag_all")
        print(dumps(policy.action(observation)), flush=True)


if __name__ == "__main__":
    main()
