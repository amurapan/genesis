import argparse
import csv
import json
from pathlib import Path

from .generation import generate
from .protocol import dumps
from .runner import run_episode
from .validation import verify_episode


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def export_episode(episode, destination):
    public = destination / "public"
    private = destination / "private"
    for key in ("manifest", "policy"):
        write_json(public / (key + ".json"), episode["public"][key])
    for key in ("truth", "provenance"):
        write_json(private / (key + ".json"), episode[key])
    for table in ("invoices", "payments"):
        (public / (table + ".jsonl")).write_text("".join(dumps(r)+"\n" for r in episode["public"][table]))
    columns = {"ledger": ["row_id", "timestamp", "account", "debit_minor", "credit_minor", "currency", "entity_id", "invoice_id", "payment_id"],
               "fx": ["date", "source_currency", "target_currency", "rate"]}
    for table, fields in columns.items():
        with (public / (table + ".csv")).open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for row in episode["public"][table]:
                writer.writerow({k: "null" if v is None else v for k, v in row.items()})


def main():
    parser = argparse.ArgumentParser(prog="sled")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("generate", "demo", "validate"):
        p = sub.add_parser(command)
        p.add_argument("--seed", type=int, default=19)
        p.add_argument("--invoices", type=int, default=50)
        p.add_argument("--clean", action="store_true")
        p.add_argument("--fixture", type=Path)
        p.add_argument("--output", type=Path, default=Path("artifacts")/command)
        if command == "demo":
            p.add_argument("--policy", choices=["reconciler", "random", "flag_all", "oracle"], default="reconciler")
            p.add_argument("--mode", choices=["train", "evaluation"], default="evaluation")
    args = parser.parse_args()
    if args.fixture:
        episode = json.loads(args.fixture.read_text())
    else:
        episode = generate(args.seed, {"invoice_count": args.invoices, "duplicate_count": 0 if args.clean else 1,
                                       "allocation_count": 0 if args.clean else 1})
    validation = verify_episode(episode)
    if args.command == "validate":
        print(json.dumps(validation, ensure_ascii=False, indent=2))
    elif args.command == "generate":
        export_episode(episode, args.output)
        print(dumps({"output": str(args.output), "valid": True, "issue_count": validation["issue_count"]}))
    else:
        result = run_episode(episode, args.policy, args.mode)
        trajectories = result.pop("trajectories")
        write_json(args.output / "private" / "report.json", result)
        (args.output / "trajectories.jsonl").write_text("".join(dumps(r)+"\n" for r in trajectories))
        print(json.dumps({k: result[k] for k in ("episode_id", "policy", "mode", "evaluation", "steps", "elapsed_seconds", "terminated", "truncated")}, indent=2))
        if result["truncated"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
