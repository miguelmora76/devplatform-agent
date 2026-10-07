"""TEST DOUBLES for the human. Used only by evals/tests; the agent package never imports these.

AutoApprover stands in for a person running `npm run approve`: it grants the approval on the
server's admin socket, which is exactly what the real command does after the person types `yes`.
"""
from agent.approval import ApprovalRequest
from agent.mcp_client import GuardrailsServer, admin_request


class AutoApprover:
    def __init__(self, server: GuardrailsServer):
        self.server = server
        self.asked: list[ApprovalRequest] = []

    async def decide(self, request: ApprovalRequest) -> bool:
        self.asked.append(request)
        reply = await admin_request(
            self.server.socket_path(), {"op": "approve", "requestId": request.request_id}
        )
        return bool(reply.get("ok"))


class DenyApprover:
    def __init__(self) -> None:
        self.asked: list[ApprovalRequest] = []

    async def decide(self, request: ApprovalRequest) -> bool:
        self.asked.append(request)
        return False
