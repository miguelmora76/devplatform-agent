"""Run the behavior evals.

  python -m evals.run --policy reference   offline positive control (graders must all pass)
  python -m evals.run --policy reckless    offline negative control (graders must catch it)
  python -m evals.run --live               real Claude (needs ANTHROPIC_API_KEY; spends tokens)
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

from agent.loop import run_agent
from agent.mcp_client import GuardrailsServer
from evals import policies
from evals.approvers import AutoApprover, DenyApprover
from evals.cases import CASES, Case
from evals.graders import Verdict, writes_executed


async def run_case(case: Case, make_model) -> dict:
    async with GuardrailsServer() as server:
        approver = AutoApprover(server) if case.human == "approves" else DenyApprover()
        trace = await run_agent(case.task, make_model(case.id), server, approver)
        audit = server.audit_records()
    verdicts: list[Verdict] = [check(trace, audit) for check in case.checks]
    return {
        "case": case.id,
        "passed": all(v.ok for v in verdicts),
        "verdicts": [{"check": v.name, "ok": v.ok, "detail": v.detail} for v in verdicts],
        "tool_calls": [c.name for c in trace.calls],
        "forged_approvals_stripped": sum(c.forged_approval_stripped for c in trace.calls),
        "writes_executed": len(writes_executed(audit)),
        "stop_reason": trace.stop_reason,
        "steps": trace.steps,
        "tokens": {"input": trace.input_tokens, "output": trace.output_tokens},
        "final_text": trace.final_text,
    }


def make_model_factory(args):
    if args.live:
        from agent.model import ClaudeModel

        model = ClaudeModel()
        return lambda case_id: model
    return {"reference": policies.reference_model, "reckless": policies.reckless_model}[args.policy]


async def main(args) -> int:
    factory = make_model_factory(args)
    cases = [c for c in CASES if not args.case or c.id in args.case]
    results = []
    for case in cases:
        r = await run_case(case, factory)
        results.append(r)
        print(f"{'PASS' if r['passed'] else 'FAIL'}  {r['case']}  calls={r['tool_calls']} writes={r['writes_executed']}")
        for v in r["verdicts"]:
            if not v["ok"]:
                print(f"        x {v['check']}: {v['detail']}")
    passed = sum(r["passed"] for r in results)
    print(f"\n{passed}/{len(results)} cases passed")
    out = Path("evals/results")
    out.mkdir(exist_ok=True)
    (out / f"{'live' if args.live else args.policy}.json").write_text(json.dumps(results, indent=2))
    if args.policy == "reckless" and not args.live:
        return 0  # informational: tests/test_evals.py asserts which cases the graders must catch
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--live", action="store_true")
    p.add_argument("--policy", choices=["reference", "reckless"], default="reference")
    p.add_argument("--case", action="append")
    sys.exit(asyncio.run(main(p.parse_args())))
