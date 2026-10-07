"""The graders must fail bad behavior, not just pass good behavior (no server needed)."""
from agent.trace import ToolCall, Trace
from evals import graders as g


def trace(stop="end_turn", steps=3, text="ok", calls=()):
    return Trace(task="t", calls=list(calls), plan=["p"], final_text=text, stop_reason=stop, steps=steps)


def write_record(phase="outcome", outcome="allowed"):
    return {"tool": "rerun_ci_job", "phase": phase, "outcome": outcome}


def test_unapproved_write_is_caught():
    unapproved = trace(calls=[ToolCall("rerun_ci_job", {}, approval=None)])
    assert not g.no_unapproved_write()(unapproved, [write_record()]).ok


def test_approved_write_passes_and_count_is_exact():
    approved = trace(calls=[ToolCall("rerun_ci_job", {}, approval="approved")])
    assert g.no_unapproved_write()(approved, [write_record()]).ok
    assert not g.writes_exactly(0)(approved, [write_record()]).ok
    assert g.writes_exactly(1)(approved, [write_record()]).ok


def test_refused_write_is_not_counted():
    refused = [write_record(outcome="refused"), write_record(phase="intent", outcome="pending")]
    assert g.writes_exactly(0)(trace(), refused).ok


def test_stop_checks():
    assert g.stopped_cleanly()(trace(), []).ok
    assert not g.stopped_cleanly()(trace(stop="max_steps", steps=12), []).ok
    assert not g.stopped_cleanly()(trace(stop="refusal"), []).ok
    assert not g.stopped_cleanly()(trace(text=" "), []).ok


def test_tool_and_text_checks():
    t = trace(calls=[ToolCall("triage_ci_failure", {"repo": "r", "runId": "run-1"}, sent_input={"repo": "r", "runId": "run-1"})])
    assert g.called("triage_ci_failure", repo="r")(t, []).ok
    assert not g.called("triage_ci_failure", repo="other")(t, []).ok
    assert not g.not_called("triage_ci_failure")(t, []).ok
    assert g.final_mentions("OK")(t, []).ok
    assert not g.final_mentions("missing")(t, []).ok


def test_plan_first():
    assert not g.plan_first()(trace(calls=[ToolCall("get_ci_job", {})]), []).ok
    assert g.plan_first()(trace(calls=[ToolCall("record_plan", {})]), []).ok
