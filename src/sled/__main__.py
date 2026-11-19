import argparse
import json
from pathlib import Path

from .generation import generate
from .protocol import dumps
from .runner import run_episode
from .validation import verify_episode
from .storage import write_json, export_episode


def main():
    parser = argparse.ArgumentParser(prog="sled")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("generate", "demo", "validate"):
        p = sub.add_parser(command)
        p.add_argument("--seed", type=int, default=19)
        p.add_argument("--invoices", type=int, default=50)
        p.add_argument("--clean", action="store_true")
        p.add_argument("--fixture", type=Path)
        p.add_argument('--config',type=Path)
        p.add_argument("--output", type=Path, default=Path("artifacts")/command)
        if command == "demo":
            p.add_argument("--policy", choices=["reconciler", "random", "flag_all", "oracle"], default="reconciler")
            p.add_argument("--mode", choices=["train", "evaluation"], default="evaluation")
    evaluate=sub.add_parser('evaluate')
    evaluate.add_argument('--output',type=Path,default=Path('artifacts/release'))
    package=sub.add_parser('package')
    package.add_argument('--report',type=Path,default=Path('artifacts/release'))
    package.add_argument('--output',type=Path,default=Path('dist/sled-submission.zip'))
    args = parser.parse_args()
    if args.command=='evaluate':
        from .release import run
        run(args.output)
        return
    if args.command=='package':
        from .packaging import build
        build(args.report,args.output)
        return
    if args.fixture:
        episode = json.loads(args.fixture.read_text())
    else:
        config = json.loads(args.config.read_text()) if args.config else {'invoice_count':args.invoices}
        if args.clean: config.update({k:0 for k in ['duplicate_count','allocation_count','fx_count','cutoff_count']})
        episode = generate(args.seed, config)
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
