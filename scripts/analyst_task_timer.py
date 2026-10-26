"""Explicit human task timer; never manufactures participants or time savings."""

import argparse
import json
import time
from pathlib import Path

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["start", "finish"])
    parser.add_argument("--session", required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--arm", choices=["manual", "caseproof"], required=True)
    parser.add_argument("--output", default="var/readiness/human-tasks.jsonl")
    parser.add_argument("--decision", default="")
    args = parser.parse_args()
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    records = [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []
    key = (args.session, args.case, args.arm)
    previous = [r for r in records if (r["session"], r["case"], r["arm"]) == key]
    if args.action == "start" and previous:
        raise SystemExit("Use a new task identity; prior measurements are preserved.")
    if args.action == "finish" and (len(previous) != 1 or not args.decision.strip()):
        raise SystemExit("A start and decision are required; correctness needs independent review.")
    record = {
        "session": args.session,
        "case": args.case,
        "arm": args.arm,
        "event": args.action,
        "wall_time": time.time(),
        "decision": args.decision,
        "correctness_reviewed": False,
    }
    if args.action == "finish":
        record["elapsed_seconds"] = record["wall_time"] - previous[0]["wall_time"]
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
    print(json.dumps(record))
