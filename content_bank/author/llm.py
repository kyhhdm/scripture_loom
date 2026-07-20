"""The single LLM seam for content-bank authoring.

Rendered prompt in, completion text out. This is the swappable/mockable ``llm()``
seam issue #16's standalone builder (``build_cli.py``) will call after
``build_brief_prompt.build(...)`` and ``build_draft_prompt.build(...)``.

Backed by ``llm_core`` (the vendored synchronous mxlens path, default model
deepseek-v4-flash). The import is lazy so that importing ``content_bank`` does
not pull litellm / langchain into processes that never make an LLM call.
"""


def llm(prompt: str, model: str | None = None) -> str:
    """Send one fully-rendered prompt, return the completion text.

    Raises RuntimeError if no LLM credential is configured (see
    ``llm_core.llm_configured``). ``model`` defaults to
    ``settings.analyst_llm_model`` (deepseek-v4-flash).
    """
    from llm_core import run_sync_llm

    return run_sync_llm("", prompt, caller="content_bank", model=model)
