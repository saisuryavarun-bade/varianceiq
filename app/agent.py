"""Agent orchestration loop.

Wraps the Anthropic Messages API in a streaming agentic loop. Yields structured
events suitable for forwarding to the frontend over SSE.

Events emitted:
    {"type": "status",      "message": str}
    {"type": "thinking",    "text": str}             # streamed text deltas
    {"type": "tool_call",   "name": str, "input": dict, "id": str}
    {"type": "tool_result", "name": str, "id": str, "result": dict}
    {"type": "final",       "markdown": str}
    {"type": "error",       "message": str}
    {"type": "done"}
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from anthropic import Anthropic

from app.config import get_settings
from app.data_loader import DataStore
from app.prompts import BRIEF_USER_PROMPT_TEMPLATE, SYSTEM_PROMPT
from app.tools import TOOLS, dispatch_tool


class VarianceAgent:
    """Autonomous variance investigator backed by Claude tool use."""

    def __init__(self, store: DataStore) -> None:
        self.settings = get_settings()
        if not self.settings.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add "
                "your key from https://console.anthropic.com/"
            )
        self.client = Anthropic(api_key=self.settings.anthropic_api_key)
        self.store = store

    def investigate(
        self, period: str = "YTD", custom_query: str | None = None
    ) -> Iterator[dict[str, Any]]:
        """Run the agent loop until the model returns end_turn."""
        user_text = custom_query or BRIEF_USER_PROMPT_TEMPLATE.format(period=period)
        messages: list[dict[str, Any]] = [{"role": "user", "content": user_text}]

        yield {"type": "status", "message": f"Starting investigation for {period}…"}

        for iteration in range(self.settings.max_agent_iterations):
            # ---- Stream one assistant turn ------------------------------------
            assistant_blocks: list[dict[str, Any]] = []
            stop_reason: str | None = None

            with self.client.messages.stream(
                model=self.settings.anthropic_model,
                max_tokens=self.settings.max_tokens_per_turn,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            ) as stream:
                for event in stream:
                    if event.type == "content_block_delta":
                        if event.delta.type == "text_delta":
                            yield {"type": "thinking", "text": event.delta.text}

                final_message = stream.get_final_message()
                stop_reason = final_message.stop_reason
                for block in final_message.content:
                    assistant_blocks.append(block.model_dump())

            messages.append({"role": "assistant", "content": assistant_blocks})

            # ---- Handle tool calls --------------------------------------------
            if stop_reason == "tool_use":
                tool_results: list[dict[str, Any]] = []
                for block in assistant_blocks:
                    if block.get("type") != "tool_use":
                        continue
                    name = block["name"]
                    args = block.get("input", {}) or {}
                    tool_id = block["id"]

                    yield {
                        "type": "tool_call",
                        "name": name,
                        "input": args,
                        "id": tool_id,
                    }

                    result = dispatch_tool(name, args, self.store)

                    yield {
                        "type": "tool_result",
                        "name": name,
                        "id": tool_id,
                        "result": result,
                    }

                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_id,
                            "content": json.dumps(result, default=str),
                        }
                    )

                messages.append({"role": "user", "content": tool_results})
                continue

            # ---- Final answer --------------------------------------------------
            if stop_reason == "end_turn":
                final_text = "".join(
                    b.get("text", "") for b in assistant_blocks if b.get("type") == "text"
                ).strip()
                yield {"type": "final", "markdown": final_text}
                yield {"type": "done"}
                return

            yield {
                "type": "error",
                "message": f"Unexpected stop_reason: {stop_reason}",
            }
            return

        yield {
            "type": "error",
            "message": (
                f"Hit max iterations ({self.settings.max_agent_iterations}) without "
                "completing investigation."
            ),
        }
