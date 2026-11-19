"""Private evaluator process. This module is absent from the agent image."""

import sys

from .protocol import dumps, loads
from .scoring import score


def main():
    state = None
    for line in sys.stdin.buffer:
        request = loads(line)
        if request["op"] == "load":
            state = request
            response = {"ready": True}
        elif request["op"] == "score" and state:
            response = score(request["submission"], state["truth"], state["evidence_ids"],
                             request["inspection_steps"], state["tolerance"])
        else:
            raise ValueError("Invalid evaluator request")
        print(dumps(response), flush=True)


if __name__ == "__main__":
    main()
