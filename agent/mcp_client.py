"""Starts the guardrails MCP server as a child process and talks to it over stdio."""
import asyncio
import json
import os
import shutil
import tempfile
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

DEFAULT_SERVER = Path(__file__).resolve().parent.parent.parent / "mcp-devplatform-guardrails" / "dist" / "bin" / "server.js"


@dataclass
class ToolOutcome:
    ok: bool
    data: Any  # structured result when ok, else the error object {code, message, requestId?}

    @property
    def error_code(self) -> str | None:
        return None if self.ok else self.data.get("code")


class GuardrailsServer:
    """One server process with its own audit file and approval socket (so runs don't mix)."""

    def __init__(self, server_js: str | Path | None = None):
        self.server_js = str(server_js or os.environ.get("GUARDRAILS_SERVER") or DEFAULT_SERVER)
        # Short path: unix sockets have a ~100 byte limit.
        self.workdir = Path(tempfile.mkdtemp(prefix="gr-"))
        self.audit_path = self.workdir / "audit.jsonl"
        self._stack = AsyncExitStack()
        self._session: ClientSession | None = None
        self.tools: list[Any] = []

    async def __aenter__(self) -> "GuardrailsServer":
        if not Path(self.server_js).exists():
            raise FileNotFoundError(
                f"{self.server_js} not found. Build the MCP server (npm ci && npm run build) "
                "or set GUARDRAILS_SERVER to its dist/bin/server.js."
            )
        env = {
            **os.environ,
            "GUARDRAILS_AUDIT_PATH": str(self.audit_path),
            "GUARDRAILS_SOCKET_DIR": str(self.workdir),
            "GUARDRAILS_LOG_LEVEL": "error",
        }
        params = StdioServerParameters(command="node", args=[self.server_js], env=env)
        errlog = open(self.workdir / "server.log", "w")  # keep the server's stderr out of the terminal
        self._stack.callback(errlog.close)
        read, write = await self._stack.enter_async_context(stdio_client(params, errlog=errlog))
        self._session = await self._stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()
        self.tools = (await self._session.list_tools()).tools
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._stack.aclose()
        shutil.rmtree(self.workdir, ignore_errors=True)

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolOutcome:
        assert self._session is not None
        result = await self._session.call_tool(name, arguments)
        data = result.structured_content
        if data is None:  # server always sends structured content; be defensive about text
            data = json.loads(result.content[0].text)
        return ToolOutcome(ok=not result.is_error, data=data)

    def socket_path(self) -> Path:
        socks = list(self.workdir.glob("*.sock"))
        if len(socks) != 1:
            raise RuntimeError(f"expected one approval socket in {self.workdir}, found {len(socks)}")
        return socks[0]

    def audit_records(self) -> list[dict[str, Any]]:
        if not self.audit_path.exists():
            return []
        return [json.loads(line) for line in self.audit_path.read_text().splitlines() if line]


async def admin_request(socket_path: Path, request: dict[str, Any]) -> dict[str, Any]:
    """One line of JSON to the server's approval socket. Only a human-side tool should call this."""
    reader, writer = await asyncio.open_unix_connection(str(socket_path))
    writer.write(json.dumps(request).encode() + b"\n")
    await writer.drain()
    reply = json.loads(await reader.readline())
    writer.close()
    return reply
