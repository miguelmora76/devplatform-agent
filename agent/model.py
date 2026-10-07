"""The model behind the loop. A protocol so evals can swap in a scripted model offline."""
from typing import Any, Protocol

MODEL = "claude-opus-5-5"


class Model(Protocol):
    async def create(self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Any:
        """Returns an object with .content (blocks), .stop_reason and .usage."""


class ClaudeModel:
    def __init__(self, model: str = MODEL):
        from anthropic import AsyncAnthropic  # imported lazily so offline tests need no credentials

        self.client = AsyncAnthropic()
        self.model = model

    async def create(self, system, messages, tools):
        return await self.client.messages.create(
            model=self.model,
            max_tokens=16000,
            system=system,
            tools=tools,
            messages=messages,
            thinking={"type": "adaptive"},
            output_config={"effort": "medium"},
        )
