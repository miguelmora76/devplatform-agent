"""Human-in-the-loop approval.

The agent can only *ask*. Granting an approval happens on the server's admin socket, which no
MCP tool exposes. `TerminalApprover` is the real flow: the person approves in a separate
terminal with the server's own `approve` command, which shows the exact action and needs a
typed `yes` on a real TTY. The evals use a clearly labelled test double (evals/approvers.py).
"""
import asyncio
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ApprovalRequest:
    tool: str
    inputs: dict[str, Any]
    request_id: str


class Approver(Protocol):
    async def decide(self, request: ApprovalRequest) -> bool:
        """True = the person says they approved it (the server still verifies); False = declined."""


class TerminalApprover:
    def __init__(self, guardrails_repo: str = "../mcp-devplatform-guardrails"):
        self.repo = guardrails_repo

    async def decide(self, request: ApprovalRequest) -> bool:
        print("\n=== APPROVAL NEEDED ===")
        print(f"The agent wants to run {request.tool} with {request.inputs}")
        print("To approve, run this in ANOTHER terminal (it asks you to type `yes`):")
        print(f"    cd {self.repo} && npm run approve -- {request.request_id}")
        answer = await asyncio.to_thread(
            input, "Press Enter once you have approved it, or type n to decline: "
        )
        return answer.strip().lower() not in {"n", "no"}
