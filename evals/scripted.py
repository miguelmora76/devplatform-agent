"""A scripted stand-in for Claude, so the loop and the graders can be checked offline.

This tests the harness and the graders (positive and negative controls). It says nothing about
how Claude behaves; that is what the live run (`make eval-live`) measures.
"""
import itertools
from dataclasses import dataclass, field
from typing import Any

_ids = itertools.count(1)


@dataclass
class Text:
    text: str
    type: str = "text"


@dataclass
class ToolUse:
    name: str
    input: dict[str, Any]
    id: str = field(default_factory=lambda: f"toolu_{next(_ids)}")
    type: str = "tool_use"


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class Response:
    content: list[Any]
    stop_reason: str
    usage: Usage = field(default_factory=Usage)


def tool_turn(*uses: ToolUse) -> Response:
    return Response(list(uses), "tool_use")


def final(text: str) -> Response:
    return Response([Text(text)], "end_turn")


class ScriptedModel:
    """Plays a fixed list of responses in order; running past the end is a test failure."""

    def __init__(self, script: list[Response]):
        self._script = iter(script)
        self.seen: list[list] = []  # snapshot of the messages sent on each turn

    async def create(self, system, messages, tools):
        self.seen.append(list(messages))
        try:
            return next(self._script)
        except StopIteration:
            raise AssertionError("agent asked for more model turns than the script has") from None


class LoopingModel:
    """Never stops calling a read tool: the max_steps guard must end it."""

    async def create(self, system, messages, tools):
        return tool_turn(ToolUse("get_ci_job", {"repo": "sample-cli-tool", "jobId": "job-3001-1"}))
