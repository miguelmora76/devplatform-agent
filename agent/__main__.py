"""Run the agent interactively:  uv run python -m agent "Plan upgrades for sample-node-api" """
import asyncio
import sys

from agent.approval import TerminalApprover
from agent.loop import run_agent
from agent.mcp_client import GuardrailsServer
from agent.model import ClaudeModel


async def main(task: str) -> None:
    async with GuardrailsServer() as server:
        trace = await run_agent(task, ClaudeModel(), server, TerminalApprover())
    print("\n--- plan ---")
    print("\n".join(f"- {s}" for s in trace.plan or []))
    print("--- tool calls ---")
    for c in trace.calls:
        print(f"{c.name} {c.sent_input or c.model_input} -> {'error ' + str(c.error_code) if c.is_error else 'ok'}"
              + (f" [approval: {c.approval}]" if c.approval else ""))
    print(f"--- final ({trace.stop_reason}, {trace.steps} steps, {trace.input_tokens}+{trace.output_tokens} tokens) ---")
    print(trace.final_text)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    asyncio.run(main(" ".join(sys.argv[1:])))
