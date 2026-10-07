"""What happened during one agent run. Evals grade this plus the server's audit log."""
from dataclasses import dataclass, field
from typing import Any

WRITE_TOOLS = frozenset({"rerun_ci_job"})


@dataclass
class ToolCall:
    name: str
    model_input: dict[str, Any]  # exactly what the model asked for
    sent_input: dict[str, Any] = field(default_factory=dict)  # what the harness actually sent
    is_error: bool = False
    error_code: str | None = None
    result: Any = None  # structured result, or the error object
    approval: str | None = None  # None | "approved" | "denied" | "not_granted"
    forged_approval_stripped: bool = False  # model supplied approvalRequestId; harness dropped it


@dataclass
class Trace:
    task: str
    calls: list[ToolCall] = field(default_factory=list)
    plan: list[str] | None = None
    final_text: str = ""
    stop_reason: str = "running"  # end_turn | max_steps | refusal | max_tokens
    steps: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def calls_to(self, name: str) -> list[ToolCall]:
        return [c for c in self.calls if c.name == name]
