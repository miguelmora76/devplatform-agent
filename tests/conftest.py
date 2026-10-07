import pytest

from agent.mcp_client import DEFAULT_SERVER
import os
from pathlib import Path

SERVER = Path(os.environ.get("GUARDRAILS_SERVER") or DEFAULT_SERVER)


def pytest_collection_modifyitems(config, items):
    if not SERVER.exists():
        skip = pytest.mark.skip(reason=f"MCP server not built at {SERVER} (set GUARDRAILS_SERVER)")
        for item in items:
            if "needs_server" in item.keywords:
                item.add_marker(skip)


def pytest_configure(config):
    config.addinivalue_line("markers", "needs_server: needs the built guardrails MCP server")
