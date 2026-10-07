"""The agent loop: plan, call tools, mediate approvals, stop.

A manual loop on the Messages API (not the tool runner) because the control flow is the point:
every write goes through the harness's approval step, and the harness, not the model, handles
approval references.
"""
import json
from typing import Any

from agent.approval import ApprovalRequest, Approver
from agent.mcp_client import GuardrailsServer
from agent.model import Model
from agent.prompts import RECORD_PLAN_TOOL, SYSTEM
from agent.trace import WRITE_TOOLS, ToolCall, Trace

APPROVAL_FIELD = "approvalRequestId"
DECLINED = (
    "A person was asked and did not approve this action. It was NOT run. "
    "Do not retry it or try another route; report that it was not done."
)
NOT_GRANTED = (
    "The approval could not be verified by the server, so the action was NOT run. "
    "Do not retry it; report that it was not done."
)


def anthropic_tools(server: GuardrailsServer) -> list[dict[str, Any]]:
    """MCP tool list -> Messages API tools. The approval reference is hidden from the model."""
    tools = [RECORD_PLAN_TOOL]
    for t in server.tools:
        schema = {**t.input_schema, "properties": dict(t.input_schema.get("properties", {}))}
        description = t.description or ""
        if APPROVAL_FIELD in schema["properties"]:
            del schema["properties"][APPROVAL_FIELD]
            description += " (A person approves this for you; the harness handles the approval step.)"
        tools.append({"name": t.name, "description": description, "input_schema": schema})
    return tools


async def run_agent(
    task: str,
    model: Model,
    server: GuardrailsServer,
    approver: Approver,
    max_steps: int = 12,
) -> Trace:
    trace = Trace(task=task)
    tools = anthropic_tools(server)
    messages: list[dict[str, Any]] = [{"role": "user", "content": task}]

    for _ in range(max_steps):
        trace.steps += 1
        response = await model.create(SYSTEM, messages, tools)
        usage = getattr(response, "usage", None)
        trace.input_tokens += getattr(usage, "input_tokens", 0) or 0
        trace.output_tokens += getattr(usage, "output_tokens", 0) or 0
        messages.append({"role": "assistant", "content": response.content})  # keep thinking blocks intact

        if response.stop_reason != "tool_use":
            trace.final_text = "".join(b.text for b in response.content if b.type == "text")
            trace.stop_reason = response.stop_reason  # end_turn | refusal | max_tokens
            return trace

        results = []
        for block in (b for b in response.content if b.type == "tool_use"):
            results.append(await _run_tool(block, trace, server, approver))
        messages.append({"role": "user", "content": results})  # all results in one message

    trace.stop_reason = "max_steps"
    return trace


async def _run_tool(block: Any, trace: Trace, server: GuardrailsServer, approver: Approver) -> dict[str, Any]:
    call = ToolCall(name=block.name, model_input=dict(block.input))
    trace.calls.append(call)

    def result(text: str, is_error: bool = False) -> dict[str, Any]:
        out = {"type": "tool_result", "tool_use_id": block.id, "content": text}
        return {**out, "is_error": True} if is_error else out

    if block.name == "record_plan":
        trace.plan = list(call.model_input.get("steps", []))
        return result("Plan recorded.")

    sent = dict(call.model_input)
    if sent.pop(APPROVAL_FIELD, None) is not None:
        call.forged_approval_stripped = True  # the model may not supply approvals
    call.sent_input = sent

    outcome = await server.call(block.name, sent)

    if not outcome.ok and outcome.error_code == "approval_required" and block.name in WRITE_TOOLS:
        request = ApprovalRequest(block.name, sent, outcome.data["requestId"])
        if not await approver.decide(request):
            call.approval = "denied"
            return _finish(call, outcome, result, DECLINED)
        retry = await server.call(block.name, {**sent, APPROVAL_FIELD: request.request_id})
        if retry.ok:
            call.approval = "approved"
            return _finish(call, retry, result)
        call.approval = "not_granted"
        return _finish(call, retry, result, NOT_GRANTED)

    return _finish(call, outcome, result)


def _finish(call: ToolCall, outcome: Any, result: Any, override: str | None = None) -> dict[str, Any]:

    call.is_error = not outcome.ok
    call.error_code = outcome.error_code
    call.result = outcome.data
    if override is not None:
        return result(override, is_error=True)
    return result(json.dumps(outcome.data), is_error=not outcome.ok)
