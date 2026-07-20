"""Pydantic schemas for the generic LLM batch endpoint.

This endpoint is intentionally minimal: caller hands in fully-rendered prompts,
endpoint dispatches one LLM call per prompt and returns raw generations. Row-
packing batch labeling lives in `llm_labeling` (datasource-backed); this is the
"arbitrary LLM call" escape hatch.

The schema also supports OpenAI/LiteLLM-style function (tool) calling:
- Pass `tools=[...]` and optional `tool_choice` on the request.
- Use `role="tool"` messages (with `tool_call_id`) to return tool results in
  multi-turn React-style loops.
- Assistant turns that called tools may have empty `content` together with a
  `tool_calls` list.
"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ChatMessage(BaseModel):
    """One turn of a chat conversation, including tool-calling support.

    For plain user / system / assistant turns, set `role` and `content`.

    For OpenAI/LiteLLM-style tool calling:
      - An assistant turn that called tools may have empty `content` and a
        non-empty `tool_calls` list (each item is the OpenAI wire shape:
        ``{id, type: 'function', function: {name, arguments}}``).
      - A tool result is sent back as ``role="tool"`` with `tool_call_id`
        identifying the call it answers, plus `content` (the tool output)
        and optional `name`.
    """

    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = Field(
        default=None,
        description="Message text. May be empty/None on assistant turns that only carry tool_calls.",
    )
    # Assistant-only — the tool calls the model wants the caller to execute.
    # Permissive shape (list[dict]) because the wire format is stable and
    # callers typically echo back what they previously received.
    tool_calls: list[dict] | None = Field(
        default=None,
        description=(
            "Assistant-only. OpenAI/LiteLLM tool-call wire shape: a list of "
            '{id, type: "function", function: {name, arguments}} dicts. '
            "`arguments` is a JSON string per the OpenAI contract."
        ),
    )
    # Tool-only — identifies which tool call this message is answering.
    tool_call_id: str | None = Field(
        default=None,
        description="Required on role='tool': the id of the assistant tool_call this message answers.",
    )
    name: str | None = Field(
        default=None,
        description="Optional tool name (used on role='tool' to disambiguate).",
    )

    @model_validator(mode="after")
    def _validate_per_role(self):
        if self.role == "tool":
            if not self.tool_call_id:
                raise ValueError("role='tool' requires tool_call_id")
            if self.content is None:
                raise ValueError("role='tool' requires content (the tool output)")
        elif self.role == "assistant":
            if not self.content and not self.tool_calls:
                raise ValueError("role='assistant' requires content or tool_calls")
        else:  # system, user
            if not self.content:
                raise ValueError(f"role='{self.role}' requires non-empty content")
        return self


# A single prompt is either a bare string (treated as a user-turn) or a full
# message list. The polymorphic shape lets simple callers stay simple while
# advanced callers retain full control over system prompts, multi-turn
# conversations, and tool calling.
PromptItem = str | list[ChatMessage]


class LLMBatchRequest(BaseModel):
    """Submit a batch of fully-rendered prompts for asynchronous LLM execution."""

    prompts: list[PromptItem] = Field(
        ...,
        min_length=1,
        description=(
            "Fully-rendered prompts. Each item is either a string (single user "
            "message) or a list of {role, content, ...} turns. Item count is "
            "capped by settings.llm_batch_max_prompts."
        ),
    )
    model: str | None = Field(
        default=None,
        description=(
            "Model id known to mxapi.chatmodels.menu (e.g. 'doubao-1.8', "
            "'deepseek-v4-lite'). Defaults to settings.llm_default_model."
        ),
    )
    config: dict | None = Field(
        default=None,
        description=(
            "LiteLLM completion overrides forwarded per call (temperature, "
            "top_p, max_tokens, async_limit, ...). Keys unknown to the model "
            "are passed through to litellm."
        ),
    )
    tools: list[dict] | None = Field(
        default=None,
        description=(
            "OpenAI/LiteLLM function-calling tool definitions. Each item is "
            '{type: "function", function: {name, description, parameters}}. '
            "Forwarded verbatim to every call in the batch."
        ),
    )
    tool_choice: str | dict | None = Field(
        default=None,
        description=(
            "Tool selection: 'auto' | 'none' | 'required' | "
            '{type: "function", function: {name}}. Forwarded verbatim.'
        ),
    )


class LLMBatchEstimateRequest(BaseModel):
    """Synchronous pre-flight token / cost estimate for a batch."""

    prompts: list[PromptItem] = Field(..., min_length=1)
    model: str | None = None
    # Allow caller to override the assumed output-token count for the
    # estimate; defaults to settings.llm_batch_estimate_output_tokens.
    output_tokens_per_prompt: int | None = Field(
        default=None,
        ge=0,
        description="Assumed completion tokens per prompt (defaults to server config).",
    )
    # Tools contribute non-trivially to input tokens; include them when present
    # so the estimate stays meaningful for tool-calling batches.
    tools: list[dict] | None = Field(
        default=None,
        description="Tool definitions (same shape as LLMBatchRequest.tools). Counted toward input tokens.",
    )


class LLMBatchEstimateResponse(BaseModel):
    """Result of `/llm/batch/estimate` — no LLM call made."""

    model: str
    num_calls: int
    input_token_total: int
    output_token_total_assumed: int
    input_price_per_token: float
    output_price_per_token: float
    estimated_cost: float
    currency_code: str
