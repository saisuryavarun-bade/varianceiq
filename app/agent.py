"""OpenAI Responses API orchestration with the existing frontend SSE contract."""
from __future__ import annotations
import json
from collections.abc import Iterator
from typing import Any
from openai import OpenAI, OpenAIError
from app.config import get_settings
from app.data_loader import DataStore
from app.prompts import BRIEF_USER_PROMPT_TEMPLATE, SYSTEM_PROMPT
from app.tools import TOOLS, dispatch_tool


class VarianceAgent:
    """Investigate using OpenAI function calls and locally computed evidence."""

    def __init__(self, store: DataStore) -> None:
        self.settings = get_settings()
        if not self.settings.openai_api_key:
            raise RuntimeError('OPENAI_API_KEY is not set. Run python scripts/configure_model.py.')
        self.client = OpenAI(api_key=self.settings.openai_api_key, timeout=120.0, max_retries=2)
        self.store = store

    def investigate(self, period: str = 'YTD', custom_query: str | None = None) -> Iterator[dict[str, Any]]:
        history = [{'role': 'user', 'content': custom_query or BRIEF_USER_PROMPT_TEMPLATE.format(period=period)}]
        yield {'type': 'status', 'message': f'Starting investigation for {period}…'}
        try:
            for _ in range(self.settings.max_agent_iterations):
                with self.client.responses.stream(
                    model=self.settings.openai_model,
                    instructions=SYSTEM_PROMPT,
                    input=history,
                    tools=TOOLS,
                    max_output_tokens=self.settings.max_tokens_per_turn,
                    store=False,
                ) as stream:
                    for event in stream:
                        if event.type == 'response.output_text.delta':
                            yield {'type': 'thinking', 'text': event.delta}
                        elif event.type in ('response.failed', 'response.incomplete', 'error'):
                            yield {'type': 'error', 'message': 'OpenAI could not finish this turn. Check model access, quota, and the output-token limit.'}
                            return
                    try:
                        response = stream.get_final_response()
                    except RuntimeError:
                        yield {'type': 'error', 'message': 'OpenAI stream ended before completing a response.'}
                        return

                if response.status != 'completed':
                    yield {'type': 'error', 'message': 'OpenAI did not complete this turn. Check the output-token limit and retry.'}
                    return
                # Preserve all output items, including reasoning, for subsequent turns.
                history.extend(item.model_dump(exclude_none=True) for item in response.output)
                calls = [item for item in response.output if item.type == 'function_call']
                if calls:
                    for call in calls:
                        try:
                            args = json.loads(call.arguments)
                            if not isinstance(args, dict):
                                raise ValueError('Arguments must be a JSON object')
                        except (ValueError, TypeError):
                            result = {'error': 'Tool arguments must be a valid JSON object.'}
                            args = {}
                        else:
                            result = dispatch_tool(call.name, args, self.store)
                        yield {'type': 'tool_call', 'name': call.name, 'input': args, 'id': call.call_id}
                        yield {'type': 'tool_result', 'name': call.name, 'result': result, 'id': call.call_id}
                        history.append({'type': 'function_call_output', 'call_id': call.call_id,
                                        'output': json.dumps(result, default=str)})
                    continue
                if not response.output_text.strip():
                    yield {'type': 'error', 'message': 'OpenAI returned no investigation text.'}
                    return
                yield {'type': 'final', 'markdown': response.output_text.strip()}
                yield {'type': 'done'}
                return
            yield {'type': 'error', 'message': f'Hit max iterations ({self.settings.max_agent_iterations}) without completing investigation.'}
        except OpenAIError:
            yield {'type': 'error', 'message': 'OpenAI request failed. Check the server API key, model access, quota, and connection.'}
        finally:
            self.client.close()
