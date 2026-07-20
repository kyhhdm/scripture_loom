import os
import hashlib
import traceback
import asyncio
from typing import Union, List
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from .basemodel import BaseModel, logger
from .basechain import BaseChain

try:
    import litellm
    from litellm import completion, acompletion, token_counter, completion_cost
    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False
    logger.warning("litellm not installed. Install with: pip install litellm")


def configure_litellm_debug(debug: bool = False):
    """
    Configure LiteLLM debug/logging settings.

    Args:
        debug: If True, enable verbose logging. If False, suppress all logging.
    """
    if not LITELLM_AVAILABLE:
        return

    import logging as _logging

    if debug:
        # Enable debug mode
        litellm.suppress_debug_info = False
        litellm.set_verbose = True
        _logging.getLogger("LiteLLM").setLevel(_logging.INFO)
        _logging.getLogger("LiteLLM Proxy").setLevel(_logging.INFO)
        _logging.getLogger("httpx").setLevel(_logging.INFO)
        logger.info("[LiteLLM] Debug mode enabled")
    else:
        # Disable LiteLLM's async logging worker to prevent event loop conflicts
        # This is necessary because we create new event loops for each batch_llm() call
        litellm.suppress_debug_info = True
        litellm.set_verbose = False
        litellm.callbacks = []  # Disable all callbacks including async logging

        # Reduce duplicate log output
        _logging.getLogger("LiteLLM").setLevel(_logging.WARNING)
        _logging.getLogger("LiteLLM Proxy").setLevel(_logging.WARNING)
        _logging.getLogger("httpx").setLevel(_logging.WARNING)


# Default: disable debug
configure_litellm_debug(debug=False)

from langchain_community.chat_message_histories import (
    SQLChatMessageHistory,
    ChatMessageHistory
)


def _extract_tool_calls(message) -> list:
    """Normalize LiteLLM's ``message.tool_calls`` into plain wire-format dicts.

    LiteLLM returns ``tool_calls`` as objects with ``.id``, ``.type``, and
    ``.function.name`` / ``.function.arguments``. Convert to JSON-friendly
    dicts so the worker can return them as part of its result envelope
    without dragging LiteLLM types across the Celery boundary.
    """
    raw = getattr(message, "tool_calls", None) or []
    out: list = []
    for tc in raw:
        if isinstance(tc, dict):
            out.append(tc)
            continue
        try:
            out.append({
                "id": getattr(tc, "id", None),
                "type": getattr(tc, "type", "function"),
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            })
        except AttributeError:
            # Unknown shape — log and drop rather than fail the whole batch.
            logger.warning(f"[_extract_tool_calls] could not normalize: {tc!r}")
    return out


class LiteLLM2Chat(BaseChain, BaseModel):
    """
    LiteLLM unified interface for multiple LLM providers.
    Supports: OpenAI, Anthropic, Azure, Cohere, Bedrock, Volcengine, etc.
    """

    batch_size_limit = 100 * 1024 * 1024  # 100M
    batch_chat_limit = 50000
    is_async_capable = True  # Flag for async-capable models

    # Default Volcengine API key (same as Volcengine2Chat)
    DEFAULT_VOLCENGINE_API_KEY = 'xxxx'
    VOLCENGINE_API_BASE = 'https://ark.cn-beijing.volces.com/api/v3'

    def __init__(self,
                 modelId='gpt-4o',
                 chat_id=None,
                 inputfile=None,
                 max_token=128000,
                 output_max_token=4096,
                 timeout=300,
                 api_key=None,
                 api_base=None,
                 provider=None,
                 async_limit=10,
                 llm_debug=False,
                 use_history=False,
                 completion_kwargs=None,
                 **kwargs
                 ) -> None:
        """
        Initialize LiteLLM chat model.

        Args:
            modelId: LiteLLM model identifier (e.g., 'gpt-4o', 'claude-3-5-sonnet-20241022',
                     'volcengine/ep-xxx' for Volcengine/Doubao models)
            chat_id: Optional session ID for chat history
            inputfile: Input file for generating session hash
            max_token: Maximum input token limit
            output_max_token: Maximum output token limit
            timeout: Request timeout in seconds
            api_key: Optional API key (uses env vars if not provided)
            api_base: Optional custom API base URL
            provider: Optional provider hint ('volcengine', 'openai', 'anthropic', etc.)
            async_limit: Maximum concurrent async API calls (default: 10)
            llm_debug: Enable LiteLLM debug logging (default: False)
            use_history: Enable SQLite chat history storage (default: False, disabled for efficiency)
        """
        if not LITELLM_AVAILABLE:
            raise ImportError("litellm is not installed. Install with: pip install litellm")

        # Configure LiteLLM debug mode
        configure_litellm_debug(debug=llm_debug)
        self.llm_debug = llm_debug

        # Detect provider from modelId if not specified
        self.provider = provider or self._detect_provider(modelId)

        # Configure provider-specific settings
        self.api_key = api_key
        self.api_base = api_base
        self.modelId = modelId  # Set before _configure_provider which may modify it
        self._configure_provider(modelId)

        self.max_token = max_token
        self.output_max_token = output_max_token
        self.timeout = timeout
        self.async_limit = async_limit
        self.completion_kwargs = dict(completion_kwargs) if completion_kwargs else {}
        self.buffer = []
        self.llm_cot = ''  # Chain of thought content
        self.input_contents = list()  # For token calculation
        self.session_id = chat_id if chat_id else self.get_dataid_hash(inputfile)
        # Default temperature: 0 for annotation (no chat_id), 0.35 for interactive chat.
        # Menu-level completion_kwargs can override via {'temperature': ...}.
        self.temperature = 0.35 if chat_id else 0

        super(LiteLLM2Chat, self).__init__(**kwargs)

        # History storage configuration
        self.use_history = use_history or (chat_id is not None)  # Enable if chat_id provided
        self.history_store = None

        if self.use_history:
            self.SQLALCHEMY_DATABASE_NAME = 'litellm_chat_sqldb.db'
            self.SQLALCHEMY_DATABASE_DIR = 'service/claudeapi/work/db/'
            self.SQLALCHEMY_DATABASE_URI = f'sqlite:///{self.SQLALCHEMY_DATABASE_DIR}{self.SQLALCHEMY_DATABASE_NAME}'
            self.check_history_store_dir()

        # Initialize clients
        self.create_llm()
        self.create_allm()
        self.reset_input_tokens()
        logger.info(f"Init LiteLLM output_max_token: {output_max_token}, max_token: {self.max_token}, model: {self.modelId}, use_history: {self.use_history}")

        if self.use_history:
            self.create_history_store(sql_model=SQLChatMessageHistory,
                                      session_id=self.session_id,
                                      connection_string=self.SQLALCHEMY_DATABASE_URI)
            self.create_conver_memory()

            if chat_id:
                self.memory_recovery()

    def _detect_provider(self, modelId: str) -> str:
        """
        Detect provider from model ID.

        Args:
            modelId: The model identifier

        Returns:
            Provider name string
        """
        if modelId.startswith('volcengine/') or modelId.startswith('ep-'):
            return 'volcengine'
        elif modelId.startswith('gpt') or modelId.startswith('o1') or modelId.startswith('openai/'):
            return 'openai'
        elif 'claude' in modelId or modelId.startswith('anthropic/'):
            return 'anthropic'
        elif modelId.startswith('deepseek/'):
            return 'deepseek'
        elif modelId.startswith('azure/'):
            return 'azure'
        elif modelId.startswith('bedrock/'):
            return 'bedrock'
        else:
            return 'openai'  # Default to OpenAI-compatible

    def _configure_provider(self, modelId: str):
        """
        Configure provider-specific settings.

        Args:
            modelId: The model identifier
        """
        if self.provider == 'volcengine':
            # Volcengine/Doubao configuration
            if not self.api_key:
                self.api_key = os.environ.get('VOLCENGINE_API_KEY',
                                              os.environ.get('ARK_API_KEY',
                                                             self.DEFAULT_VOLCENGINE_API_KEY))
            if not self.api_base:
                self.api_base = self.VOLCENGINE_API_BASE

            # Ensure model ID has volcengine/ prefix for LiteLLM
            if not modelId.startswith('volcengine/'):
                self.modelId = f'volcengine/{modelId}'
            else:
                self.modelId = modelId

            logger.info(f"Configured Volcengine provider: model={self.modelId}, api_base={self.api_base}")

        elif self.provider == 'deepseek':
            # DeepSeek configuration
            if not self.api_key:
                self.api_key = os.environ.get('DEEPSEEK_API_KEY')
            if not self.api_base:
                self.api_base = 'https://api.deepseek.com'

    def create_llm(self):
        """Create sync LiteLLM client (LiteLLM uses functional API)."""
        # LiteLLM uses functional API, no client object needed
        # Configure optional settings based on provider
        if self.api_key:
            if self.provider == 'volcengine':
                os.environ.setdefault('VOLCENGINE_API_KEY', self.api_key)
            elif self.provider == 'openai':
                os.environ.setdefault('OPENAI_API_KEY', self.api_key)
            elif self.provider == 'anthropic':
                os.environ.setdefault('ANTHROPIC_API_KEY', self.api_key)
            elif self.provider == 'deepseek':
                os.environ.setdefault('DEEPSEEK_API_KEY', self.api_key)

        self.llm = None  # Placeholder for compatibility

    def create_allm(self):
        """Create async LiteLLM client (uses same functional API)."""
        self.allm = None  # Placeholder for compatibility

    def create_conver_memory(self):
        self.buff = []

    def check_history_store_dir(self):
        """Create DB directory if not exists."""
        if not os.path.exists(self.SQLALCHEMY_DATABASE_DIR):
            os.makedirs(self.SQLALCHEMY_DATABASE_DIR)

    def get_dataid_hash(self, dataid):
        """Generate session ID hash."""
        if dataid is None:
            dataid = 'default'
        return hashlib.md5(dataid.encode()).hexdigest()

    def _build_completion_kwargs(self, **overrides) -> dict:
        """Merge defaults, per-model completion_kwargs, and caller overrides.

        Precedence (lowest → highest): class default (temperature) → menu-level
        completion_kwargs → per-call overrides.
        """
        params = {'temperature': self.temperature}
        params.update(self.completion_kwargs)
        params.update(overrides)
        return params

    def chat(self, msg, *args, **kwargs) -> [str, bool]:
        """
        Synchronous chat with token truncation logic.
        """
        tokens_num = self.get_num_tokens(msg)
        logger.info(f'msg_len: {len(msg)}, token_len: {tokens_num}')
        max_token = int(self.max_token * 0.9)

        # Truncate message if exceeds token limit
        while tokens_num > max_token:
            # Estimate characters to cut based on token ratio
            cut_chars = int((tokens_num - max_token) * 1.5)
            msg = msg[:-cut_chars] if cut_chars < len(msg) else msg[:max_token]
            tokens_num = self.get_num_tokens(msg)

        logger.info(f'after msg_len: {len(msg)}, token_len: {tokens_num}')
        try:
            res = self.llm_chat(self.buffer + [{"role": "user", "content": msg}], user_msg=msg)
        except Exception as e:
            res = None
            logger.info(f'Error {e}')

        return (res, True) if res else (f'{self.modelId} Error', False)

    def llm_chat(self, msg, user_msg, save_memory=True, CoT=False, **kwargs) -> str:
        """
        Core LLM call using litellm.completion() - synchronous version.
        """
        import time
        start_time = time.time()
        logger.info(f'[llm_chat] start model={self.modelId}')

        try:
            # Build optional params
            optional_params = {}
            if self.api_key:
                optional_params['api_key'] = self.api_key
            if self.api_base:
                optional_params['api_base'] = self.api_base

            result = completion(
                model=self.modelId,
                messages=msg,
                max_tokens=self.output_max_token,
                timeout=self.timeout,
                **self._build_completion_kwargs(**kwargs),
                **optional_params,
            )

            elapsed = round(time.time() - start_time, 2)
            tokens_in = result.usage.prompt_tokens if result.usage else 0
            tokens_out = result.usage.completion_tokens if result.usage else 0
            finish_reason = result.choices[0].finish_reason if result.choices else 'unknown'

            logger.info(f'[llm_chat] end elapsed={elapsed}s, tokens_in={tokens_in}, tokens_out={tokens_out}, finish={finish_reason}')

            if result and result.choices and result.choices[0].message:
                if CoT and hasattr(result.choices[0].message, 'reasoning_content'):
                    self.llm_cot = getattr(result.choices[0].message, 'reasoning_content', '')
                    logger.info(f"[llm_chat] CoT: {self.llm_cot}")

                msg += [{"role": "assistant", "content": result.choices[0].message.content}]

                # Handle length limit (continue generation if needed)
                try:
                    if result.choices[0].finish_reason == "length":
                        logger.warning(f'[llm_chat] truncated (finish_reason=length), continuing...')
                        loop_num = 0
                        loop_limit = 10
                        repet_result = self.detect_repetition_efficient(result.choices[0].message.content)

                        while (result.choices[0].finish_reason == "length" and
                               loop_num < loop_limit and
                               repet_result.get('repetition_type') is False):
                            result = completion(
                                model=self.modelId,
                                messages=msg,
                                max_tokens=self.output_max_token,
                                timeout=self.timeout,
                                **self._build_completion_kwargs(**kwargs),
                                **optional_params,
                            )
                            msg[-1]["content"] += result.choices[0].message.content
                            repet_result = self.detect_repetition_efficient(msg[-1]["content"])
                            loop_num += 1
                            logger.info(f'[llm_chat] continuation {loop_num}, finish={result.choices[0].finish_reason}')
                except Exception as e:
                    logger.error(f'[llm_chat] continuation error: {e}')
                    raise Exception(f'Error {traceback.format_exc()}')

                resp_msg = msg[-1]["content"]

                if save_memory and self.use_history and self.history_store is not None:
                    self.history_store.add_messages([HumanMessage(user_msg),
                                                     AIMessage(resp_msg)])
                return resp_msg
            else:
                return f'---> {result}'

        except Exception as e:
            elapsed = round(time.time() - start_time, 2)
            logger.error(f'[llm_chat] error elapsed={elapsed}s, error={e}')
            raise

    async def allm_chat(self, msg, CoT=False, task_id=0, **call_overrides) -> None:
        """
        Async version using litellm.acompletion().

        ``call_overrides`` are forwarded to :meth:`_build_completion_kwargs`,
        overriding any same-named entry in the menu-level ``completion_kwargs``.
        Reserved names: ``CoT``, ``task_id`` (positional params of this method).
        """
        import time
        start_time = time.time()
        logger.info(f'[allm_chat] start task_id={task_id}, model={self.modelId}')

        try:
            # Build optional params
            optional_params = {}
            if self.api_key:
                optional_params['api_key'] = self.api_key
            if self.api_base:
                optional_params['api_base'] = self.api_base

            result = await acompletion(
                model=self.modelId,
                messages=msg,
                max_tokens=self.output_max_token,
                timeout=self.timeout,
                **self._build_completion_kwargs(**call_overrides),
                **optional_params,
            )

            elapsed = round(time.time() - start_time, 2)
            if result.usage:
                tokens_in = result.usage.prompt_tokens
                tokens_out = result.usage.completion_tokens
            else:
                # 200 OK but no usage block. Estimate from text so the row
                # contributes a visible, non-zero figure instead of a silent 0
                # that under-counts cost + the daily quota (issue #54).
                prompt_text = " ".join(
                    (m.get("content") or "") for m in msg if isinstance(m, dict)
                )
                resp_text = ""
                if result.choices and result.choices[0].message:
                    resp_text = result.choices[0].message.content or ""
                tokens_in = self.get_num_tokens(prompt_text)
                tokens_out = self.get_num_tokens(resp_text)
                logger.warning(
                    f'[allm_chat] task_id={task_id} response had no usage block; '
                    f'estimated tokens_in={tokens_in}, tokens_out={tokens_out} from text'
                )
            finish_reason = result.choices[0].finish_reason if result.choices else 'unknown'

            logger.info(f'[allm_chat] end task_id={task_id}, elapsed={elapsed}s, '
                       f'tokens_in={tokens_in}, tokens_out={tokens_out}, finish={finish_reason}')

            # Stash usage on the AIMessage so the runner can aggregate it
            # without re-reading the structured log (issue #26 Layer 0).
            usage_dict = {"tokens_in": int(tokens_in), "tokens_out": int(tokens_out)}

            if result and result.choices and result.choices[0].message:
                if CoT and hasattr(result.choices[0].message, 'reasoning_content'):
                    logger.info(f"[allm_chat] task_id={task_id} CoT: {getattr(result.choices[0].message, 'reasoning_content', '')}")

                msg += [{"role": "assistant", "content": result.choices[0].message.content}]

                tool_calls = _extract_tool_calls(result.choices[0].message)

                finish_reason = result.choices[0].finish_reason
                if finish_reason == "length":
                    resp_msg = '{}'
                    logger.warning(f'[allm_chat] task_id={task_id} truncated (finish_reason=length)')
                elif finish_reason == "stop":
                    resp_msg = msg[-1]["content"] or ""
                elif finish_reason in ("tool_calls", "function_call"):
                    # Tool-call response: content may be None when the model
                    # returned only tool_calls. Carry the (possibly empty)
                    # text through; the tool_calls themselves ride on
                    # additional_kwargs.
                    resp_msg = result.choices[0].message.content or ""
                else:
                    logger.warning(f"[allm_chat] task_id={task_id} unexpected finish_reason={finish_reason}")
                    resp_msg = '{}'
            else:
                tool_calls = []
                resp_msg = '{}'

            ai_msg = AIMessage(resp_msg)
            if tool_calls:
                ai_msg.additional_kwargs["tool_calls"] = tool_calls
            ai_msg.additional_kwargs["usage"] = usage_dict
            # Stash the model's chain-of-thought so llm_trace can surface it
            # (issue #57). Only when non-empty — keeps additional_kwargs clean
            # for non-thinking responses.
            if result and result.choices and result.choices[0].message:
                reasoning = getattr(
                    result.choices[0].message, 'reasoning_content', None
                )
                if reasoning:
                    ai_msg.additional_kwargs["reasoning_content"] = reasoning
            self.abatch_result.append(ai_msg)
            return ai_msg

        except Exception as e:
            elapsed = round(time.time() - start_time, 2)
            logger.error(f'[allm_chat] error task_id={task_id}, elapsed={elapsed}s, error={e}')
            ai_msg = AIMessage('{}')
            # Surface a zero-usage marker so the aggregator stays sound on
            # provider errors — a missing key would silently skew the
            # quota true-up.
            ai_msg.additional_kwargs["usage"] = {"tokens_in": 0, "tokens_out": 0}
            self.abatch_result.append(ai_msg)
            return ai_msg

    def get_num_tokens(self, msg: str, direct=True) -> int:
        """
        Token counting via litellm.token_counter().

        Args:
            msg: Text to count tokens for
            direct: If True, count immediately; if False, buffer for batch counting
        """
        if direct:
            try:
                # LiteLLM token_counter expects messages format
                messages = [{"role": "user", "content": msg}]

                # For Volcengine models, use a compatible model for token counting
                # since LiteLLM may not have exact tokenizer for Volcengine
                if self.provider == 'volcengine':
                    # Use GPT-4 tokenizer as approximation for Doubao
                    # (both use similar BPE tokenization)
                    return token_counter(model='gpt-4', messages=messages)
                else:
                    return token_counter(model=self.modelId, messages=messages)
            except Exception as e:
                # Fallback: estimate based on character count
                # Chinese text averages ~1.5 tokens per character
                logger.warning(f"Token counting failed, using estimate: {e}")
                return int(len(msg) / 1.5)  # Better estimate for Chinese text
        else:
            self.input_contents.append(f'{msg}')
            return 0

    def reset_input_tokens(self):
        self.input_token_num = 0

    def cal_input_tokens(self):
        """Calculate total input tokens for buffered content."""
        for content in self.input_contents:
            self.input_token_num += self.get_num_tokens(content, direct=True)
        logger.info(f'length of input_contents: {len(self.input_contents)}, total tokens: {self.input_token_num}')

    def get_prompt_cost(self, *args, **kwargs):
        """Calculate cost for current conversation."""
        if not self.input_contents:
            return 0
        self.cal_input_tokens()
        return self.input_price * self.input_token_num

    def clear_history(self):
        """Clear chat history."""
        if self.history_store is not None:
            self.history_store.clear()

    def new_chat(self):
        if self.use_history:
            self.clear_history()
        self.buff = []
        return self.session_id, ''

    def format_Message2litellm(self, msg):
        """Convert one chat turn into LiteLLM's wire-level message dict.

        Accepts:
            - LangChain Message objects (HumanMessage / AIMessage /
              SystemMessage): mapped via the base ``format_Message``.
            - Plain dicts already in LiteLLM/OpenAI format (with keys
              ``role`` / ``content`` plus optional ``tool_calls`` /
              ``tool_call_id`` / ``name``): returned unchanged. This lets
              tool-calling callers (``/api/v1/llm/batch``) build the raw
              wire shape directly — LangChain's text-only message classes
              can't express ``role='tool'`` or assistant turns that carry
              ``tool_calls`` without text content.
        """
        if isinstance(msg, dict):
            return msg
        return self.format_Message(msg)

    def memory_recovery(self):
        """Recover conversation buffer from history."""
        if self.history_store is None:
            logger.warning('memory_recovery called but history_store is None')
            return

        history_buffer = (self.history_store.messages[:2]
                         if len(self.history_store.messages) < 4
                         else self.history_store.messages[:2] + self.history_store.messages[-2:])

        buffer = [self.format_Message2litellm(msg) for msg in history_buffer]
        self.buffer = buffer
        logger.info(f'recover buffer: {self.buffer}')

    def check_batch_size(self, batch_list):
        return super().check_batch_size(batch_list)

    def _per_call_timeout(self) -> float:
        """Hard asyncio-level ceiling (seconds) for a single ``allm_chat``.

        Set above ``self.timeout`` so litellm's own per-request timeout fires
        first and reports a clean provider error; this wait_for boundary is
        only the backstop for when that internal timeout does not fire.
        Overridable in tests to exercise the timeout path quickly.
        """
        return (self.timeout or 300) + 60

    def batch_llm(self, msgs: list, **call_overrides):
        """Batch processing using async gather.

        Dispatches the coroutine to a dedicated background-thread event loop
        (see ``_aio_runner``). This is safe under a gevent Celery worker,
        where multiple concurrent greenlets in one OS thread would otherwise
        collide on asyncio's thread-local running-loop state.

        ``call_overrides`` are LiteLLM completion parameters (e.g. ``top_p``,
        ``reasoning_effort``) forwarded to every underlying ``acompletion``
        call. They take precedence over the menu-level ``completion_kwargs``.
        """
        import time
        try:
            from celery.exceptions import SoftTimeLimitExceeded
        except ModuleNotFoundError:
            # celery is not a dependency of scripture_loom's llm_core. Define a
            # sentinel the `except SoftTimeLimitExceeded` clause below can never
            # match, so batch_llm runs identically without Celery.
            class SoftTimeLimitExceeded(BaseException):
                pass

        from . import _aio_runner

        start_time = time.time()
        self.abatch_result = []
        logger.info(f'[batch_llm] start msgs_count={len(msgs)}, model={self.modelId}')

        try:
            _aio_runner.run_coro(self.abatch_llm(msgs, **call_overrides))
        except SoftTimeLimitExceeded:
            # The soft-time-limit watchdog injects this into the greenlet while
            # it's parked in run_coro (mxlens issue #31). It MUST propagate so
            # Celery terminates the task and frees the slot/lease. The generic
            # handler below catches Exception — which SoftTimeLimitExceeded
            # subclasses — so without this clause the watchdog is a silent no-op
            # on the primary annotate path and the task returns normally.
            raise
        except Exception:
            logger.error(f'[batch_llm] error: {traceback.format_exc()}')

        elapsed = round(time.time() - start_time, 2)
        logger.info(f'[batch_llm] end msgs_count={len(msgs)}, results_count={len(self.abatch_result)}, elapsed={elapsed}s')
        return self.abatch_result

    async def abatch_llm(self, msgs: list, *args, **call_overrides):
        """Async batch processing with concurrency control.

        ``call_overrides`` are forwarded to every ``allm_chat`` (and thence to
        ``acompletion``). See :meth:`batch_llm` for precedence rules.
        """
        import time
        start_time = time.time()
        async_limit = self.async_limit
        CoT = True if len(msgs) <= 5 else False
        total_batches = (len(msgs) + async_limit - 1) // async_limit
        ordered_results = []

        logger.info(f'[abatch_llm] start msgs_count={len(msgs)}, async_limit={async_limit}, total_batches={total_batches}')

        # Hard per-call ceiling that does NOT depend on litellm honoring its
        # own `timeout`. asyncio.wait_for runs on the dedicated _aio_runner
        # loop (a real OS thread), so it cancels a stalled acompletion even
        # when litellm's internal timeout fails to fire — the exact failure
        # that left annotate chunks hung for hours and wedged the gevent pool
        # (see mxlens issue #31).
        call_timeout = self._per_call_timeout()

        # Process in batches of async_limit
        for i in range(0, len(msgs), async_limit):
            batch = msgs[i:i + async_limit]
            batch_num = i // async_limit + 1
            logger.info(f'[abatch_llm] batch {batch_num}/{total_batches} start, size={len(batch)}')

            batch_start = time.time()
            results = await asyncio.gather(*(
                asyncio.wait_for(
                    self.allm_chat(
                        [self.format_Message2litellm(chat_) for chat_ in msg_],
                        CoT=CoT,
                        task_id=i + idx,
                        **call_overrides,
                    ),
                    timeout=call_timeout,
                )
                for idx, msg_ in enumerate(batch)
            ), return_exceptions=True)  # wait_for caps each call; gather absorbs timeouts as exceptions

            batch_elapsed = round(time.time() - batch_start, 2)

            # Log any exceptions
            errors = sum(1 for r in results if isinstance(r, Exception))
            if errors:
                logger.error(f'[abatch_llm] batch {batch_num}/{total_batches} had {errors} errors')
            logger.info(f'[abatch_llm] batch {batch_num}/{total_batches} end, elapsed={batch_elapsed}s, errors={errors}')

            # Collect ordered results from gather (input order preserved)
            ordered_results.extend(
                r if isinstance(r, AIMessage) else AIMessage('{}')
                for r in results
            )

        # Override side-effect list with input-ordered results from gather
        self.abatch_result = ordered_results

        elapsed = round(time.time() - start_time, 2)
        logger.info(f'[abatch_llm] end results_count={len(self.abatch_result)}, elapsed={elapsed}s')
