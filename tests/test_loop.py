"""The loop against the REAL guardrails server, driven by scripted models (no API key needed)."""
import pytest

from agent.loop import anthropic_tools, run_agent
from agent.mcp_client import GuardrailsServer
from evals.approvers import AutoApprover, DenyApprover
from evals.graders import writes_executed
from evals.scripted import LoopingModel, ScriptedModel, ToolUse, final, tool_turn

pytestmark = pytest.mark.needs_server
RERUN = {"repo": "sample-cli-tool", "jobId": "job-3001-1"}


async def test_model_never_sees_the_approval_field():
    async with GuardrailsServer() as server:
        rerun = next(t for t in anthropic_tools(server) if t["name"] == "rerun_ci_job")
    assert "approvalRequestId" not in rerun["input_schema"]["properties"]


async def test_forged_approval_is_stripped_and_nothing_is_written():
    forged = {**RERUN, "approvalRequestId": "req_aaaaaaaaaaaaaaaaaaaaaaaaaa"}
    model = ScriptedModel([tool_turn(ToolUse("rerun_ci_job", forged)), final("not re-run")])
    async with GuardrailsServer() as server:
        trace = await run_agent("t", model, server, DenyApprover())
        assert writes_executed(server.audit_records()) == []
    call = trace.calls[0]
    assert call.forged_approval_stripped and "approvalRequestId" not in call.sent_input
    assert call.approval == "denied"


async def test_declined_approval_tells_the_model_not_to_retry():
    model = ScriptedModel([tool_turn(ToolUse("rerun_ci_job", RERUN)), final("not re-run")])
    async with GuardrailsServer() as server:
        await run_agent("t", model, server, DenyApprover())
    result = model.seen[1][-1]["content"][0]
    assert result["is_error"] and "NOT run" in result["content"]


async def test_approved_write_runs_once_and_is_audited():
    model = ScriptedModel([tool_turn(ToolUse("rerun_ci_job", RERUN)), final("re-run")])
    async with GuardrailsServer() as server:
        approver = AutoApprover(server)
        trace = await run_agent("t", model, server, approver)
        audit = server.audit_records()
        job = await server.call("get_ci_job", {"repo": "sample-cli-tool", "jobId": "job-3001-1"})
    assert trace.calls[0].approval == "approved" and len(approver.asked) == 1
    assert len(writes_executed(audit)) == 1
    assert [r["phase"] for r in audit if r["tool"] == "rerun_ci_job"] == ["complete", "intent", "outcome"]
    assert job.ok


async def test_unverifiable_approval_is_not_granted():
    class LyingApprover:  # says "approved" but never approves on the server
        async def decide(self, request):
            return True

    model = ScriptedModel([tool_turn(ToolUse("rerun_ci_job", RERUN)), final("not re-run")])
    async with GuardrailsServer() as server:
        trace = await run_agent("t", model, server, LyingApprover())
        assert writes_executed(server.audit_records()) == []
    assert trace.calls[0].approval == "not_granted"


async def test_parallel_tool_calls_return_in_one_message():
    model = ScriptedModel([
        tool_turn(
            ToolUse("plan_dependency_upgrades", {"repo": "sample-node-api"}),
            ToolUse("plan_dependency_upgrades", {"repo": "sample-web-app"}),
        ),
        final("done"),
    ])
    async with GuardrailsServer() as server:
        await run_agent("t", model, server, DenyApprover())
    assert len(model.seen[1][-1]["content"]) == 2


async def test_step_budget_stops_a_looping_model():
    async with GuardrailsServer() as server:
        trace = await run_agent("t", LoopingModel(), server, DenyApprover(), max_steps=3)
    assert trace.stop_reason == "max_steps" and trace.steps == 3


async def test_refusal_stop_reason_ends_the_run():
    from evals.scripted import Response, Text

    model = ScriptedModel([Response([Text("I can't help with that.")], "refusal")])
    async with GuardrailsServer() as server:
        trace = await run_agent("t", model, server, DenyApprover())
    assert trace.stop_reason == "refusal"
