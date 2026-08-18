"""CLI entrypoint.

    python -m copilot "I need a Postgres for staging, ~50GB, bursty" --team checkout
    python -m copilot "..." --team checkout --offline     # no Bedrock call
    python -m copilot "..." --team checkout --open-pr      # open a real PR
"""
from __future__ import annotations

import argparse
import json
import sys

from . import pipeline


def _print_plan(result: dict) -> None:
    sizing = result["sizing"]
    cost = result["cost"]
    budget = result["budget"]
    policy = result["policy"]
    print(f"\n  request:  {result['request_id']}")
    print(f"  module:   {sizing['module']}  ({result['intent']['kind']}, "
          f"{result['intent']['environment']})")
    if sizing["instance_type"]:
        print(f"  instance: {sizing['instance_type']}  storage: "
              f"{sizing['storage_gb']}GB {sizing['storage_class']}")
    print(f"  cost:     ~${cost['monthly_usd']:.2f}/mo  ({cost['source']})")
    print(f"  budget:   [{budget['verdict'].upper()}] {budget['message']}")
    verdict = "PASS" if policy["passed"] else "BLOCKED"
    print(f"  policy:   [{verdict}] ({policy['engine']})")
    for v in policy["violations"]:
        print(f"              - {v}")
    print("\n  rationale:")
    for r in sizing["rationale"]:
        print(f"    - {r}")
    if sizing["cheaper_alternative"]:
        print(f"    ~ {sizing['cheaper_alternative']}")
    print("\n  artifacts:")
    for k, v in result["outputs"].items():
        if v:
            print(f"    {k}: {v}")
    print()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="copilot", description=__doc__)
    p.add_argument("request", help="Plain-language description of the resource")
    p.add_argument("--team", required=True, help="Requesting team (cost center key)")
    p.add_argument("--offline", action="store_true",
                   help="Skip Bedrock; use the keyword classifier")
    p.add_argument("--open-pr", action="store_true", help="Open a real PR via gh")
    p.add_argument("--approve", action="store_true",
                   help="Attach an approval label (over-budget/GPU override)")
    p.add_argument("--json", action="store_true", help="Emit raw JSON")
    args = p.parse_args(argv)

    if args.offline:
        intent, team = pipeline.classify(args.request, args.team)
        result = pipeline.run(intent, team, approval_label=args.approve,
                              open_pr=args.open_pr)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            _print_plan(result)
        return 0 if result["policy"]["passed"] else 2

    # Online: drive the Bedrock tool-use loop.
    from . import agent
    out = agent.run(args.request, args.team, auto_submit=True)
    print(out["final_text"])
    if out["submit_result"]:
        if args.json:
            print(json.dumps(out["submit_result"], indent=2))
        else:
            _print_plan(out["submit_result"])
        return 0 if out["submit_result"]["policy"]["passed"] else 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
