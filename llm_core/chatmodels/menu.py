import importlib

# Lazy import mapping: class name -> module path
# Classes are imported on-demand to avoid requiring all dependencies upfront
# Trimmed for scripture_loom's llm_core: only the LiteLLM path (all active menu
# entries) plus the Fake stub are vendored. BedRock2Chat / OpenAi2Chat /
# Volcengine2Chat were left behind (their provider modules and heavy deps are
# not needed for the deepseek-v4-flash sync path).
_CLASS_MODULES = {
    "Fake2Chat": ".fakemodel",
    "LiteLLM2Chat": ".LiteLLM",
}

# Cache for lazily loaded classes (module-level for __getattr__ access)
_class_cache = {}


def __getattr__(name: str):
    """Enable lazy class loading for backward compatibility.

    This allows code like `isinstance(obj, menu.Volcengine2Chat)` to work
    without requiring all dependencies to be installed upfront.
    """
    if name in _CLASS_MODULES:
        if name not in _class_cache:
            module = importlib.import_module(_CLASS_MODULES[name], package="llm_core.chatmodels")
            _class_cache[name] = getattr(module, name)
        return _class_cache[name]
    raise AttributeError(f"module 'mxapi.chatmodels.menu' has no attribute '{name}'")


# Active entries: LiteLLM2Chat (current main client) + a set of
# Volcengine2Chat / OpenAi2Chat endpoints migrated from the former mxconfig
# integration. Historical non-LiteLLM entries are kept commented below for
# reference.
inner_menu = {
    # --- BedRock2Chat entries (commented out) ---
    # 'claude3-haiku': {'id': 'anthropic.claude-3-haiku-20240307-v1:0',
    #                   'max_token': 200000,
    #                   'input_price': 0.00025 / 1000,
    #                   'output_price': 0.00125 / 1000,
    #                   'currency_code': 'USD',
    #                   'clsType': 'BedRock2Chat'},  # claude3_haiku
    #
    # 'claude3-sonnet': {'id': 'anthropic.claude-3-sonnet-20240229-v1:0',
    #                    'max_token': 200000,
    #                    'input_price': 0.003 / 1000,
    #                    'output_price': 0.015 / 1000,
    #                    'currency_code': 'USD',
    #                    'clsType': 'BedRock2Chat'},  # claude3_sonnet
    #
    # 'claude3_5-sonnet': {'id': 'anthropic.claude-3-5-sonnet-20240620-v1:0',
    #                      'max_token': 200000,
    #                      'input_price': 0.003 / 1000,
    #                      'output_price': 0.015 / 1000,
    #                      'currency_code': 'USD',
    #                      'clsType': 'BedRock2Chat'},  # Claude 3.5 Sonnet
    #
    # 'claude1-instant': {'id': 'anthropic.claude-instant-v1',
    #                     'max_token': 100000,
    #                     'input_price': 0.0008 / 1000,
    #                     'output_price': 0.0024 / 1000,
    #                     'currency_code': 'USD',
    #                     'clsType': 'BedRock2Chat'},  # claude_instant
    # --- OpenAi2Chat entries (commented out) ---
    # 'chatgpt-4o-513': {'id': 'gpt-4o-2024-05-13',
    #                     'output_max_token': 4096,
    #                     'max_token': 100000,
    #                     'input_price': 0.005 / 1000,
    #                     'output_price': 0.015 / 1000,
    #                     'currency_code': 'USD',
    #                     'clsType': 'OpenAi2Chat'},  # OpenAi chatgpt
    #
    # 'chatgpt-4o-806': {'id': 'gpt-4o-2024-08-06',
    #                     'output_max_token': 16384,
    #                     'max_token': 100000,
    #                     'input_price': 0.0025 / 1000,
    #                     'output_price': 0.01 / 1000,
    #                     'currency_code': 'USD',
    #                     'clsType': 'OpenAi2Chat'},  # OpenAi chatgpt
    #
    # 'chatgpt-4o': {'id': 'gpt-4o',
    #                'output_max_token': 16384,
    #                'max_token': 100000,
    #                'input_price': 0.0025 / 1000,
    #                'output_price': 0.01 / 1000,
    #                'currency_code': 'USD',
    #                'clsType': 'OpenAi2Chat'},  # OpenAi chatgpt
    # --- Volcengine2Chat entries (commented out) ---
    # 'doubao-pro-256k': {'id': 'ep-20241113161554-rmbb4',
    #                     'output_max_token': 4096,  # doubao 共用input和output
    #                     'max_token': 230000,
    #                     'input_price': 0.005 / 1000,
    #                     'output_price': 0.009 / 1000,
    #                     'currency_code': 'CNY',
    #                     'clsType': 'Volcengine2Chat'},  # Volcengine doubao
    #
    # 'doubao-pro-32k': {'id': 'ep-20250113140612-jkktp',
    #                     'output_max_token': 4096,  # doubao 共用input和output
    #                     'max_token': 28000,
    #                     'input_price': 0.0008 / 1000,
    #                     'output_price': 0.0002 / 1000,
    #                     'currency_code': 'CNY',
    #                     'clsType': 'Volcengine2Chat'},  # Volcengine doubao
    #
    # 'doubao-1.5pro-32k': {
    #                     'id': 'ep-20250610184034-vxkh4',
    #                     'output_max_token': 12288,  # doubao 共用input和output
    #                     'max_token': 100000,
    #                     'input_price': 0.0008 / 1000,
    #                     'output_price': 0.0002 / 1000,
    #                     'currency_code': 'CNY',
    #                     'clsType': 'Volcengine2Chat'},  # Volcengine doubao
    #
    # 'mxbusiness-doubao-1.5pro-32k': {
    #                     'id': 'ep-20250610184219-zl8k8',
    #                     'output_max_token': 12288,  # doubao 共用input和output
    #                     'max_token': 100000,
    #                     'input_price': 0.0008 / 1000,
    #                     'output_price': 0.0002 / 1000,
    #                     'currency_code': 'CNY',
    #                     'clsType': 'Volcengine2Chat'},  # Volcengine doubao
    #
    # 'doubao-1.5pro-256k': {'id': 'ep-20250513104638-s4nkq',
    #                     'output_max_token': 12288,  # doubao 共用input和output
    #                     'max_token': 230000,
    #                     'input_price': 0.0008 / 1000,
    #                     'output_price': 0.0002 / 1000,
    #                     'currency_code': 'CNY',
    #                     'clsType': 'Volcengine2Chat'},  # Volcengine doubao
    #
    # 'deepseek-r1': {'id': 'ep-20250213140047-fr476',
    #                 'output_max_token': 8000,  # doubao 128k共用input和output
    #                 'max_token': 60000,
    #                 'input_price': 0.004 / 1000,
    #                 'output_price': 0.016 / 1000,
    #                 'currency_code': 'CNY',
    #                 'clsType': 'Volcengine2Chat'},  # Volcengine doubao
    #
    # 'deepseek-v3': {'id': 'ep-20250513102813-stmk6',
    #                 'output_max_token': 8192,  # doubao 128k共用input和output
    #                 'max_token': 100000,  # 128k
    #                 'input_price': 0.002 / 1000,
    #                 'output_price': 0.008 / 1000,
    #                 'currency_code': 'CNY',
    #                 'clsType': 'Volcengine2Chat'},  # Volcengine doubao
    # --- Fake2Chat stub (commented out) ---
    # 'testmodel': {'id': None,
    #               'max_token': None,
    #               'input_price':0,
    #               'output_price':0,
    #               'clsType': 'Fake2Chat'},  # test model
    # LiteLLM models - unified interface for multiple providers
    #"gpt-4o": {
    #    "id": "gpt-4o",
    #    "output_max_token": 16384,
    #    "max_token": 128000,
    #    "input_price": 0.0025 / 1000,
    #    "output_price": 0.01 / 1000,
    #    "currency_code": "USD",
    #    "clsType": "LiteLLM2Chat",
    #},
    #"gpt-4o-mini": {
    #    "id": "gpt-4o-mini",
    #    "output_max_token": 16384,
    #    "max_token": 128000,
    #    "input_price": 0.00015 / 1000,
    #    "output_price": 0.0006 / 1000,
    #    "currency_code": "USD",
    #    "clsType": "LiteLLM2Chat",
    #},
    #"claude-sonnet": {
    #    "id": "claude-3-5-sonnet-20241022",
    #    "output_max_token": 8192,
    #    "max_token": 200000,
    #    "input_price": 0.003 / 1000,
    #    "output_price": 0.015 / 1000,
    #    "currency_code": "USD",
    #    "clsType": "LiteLLM2Chat",
    #},
    #"claude-haiku": {
    #    "id": "claude-3-5-haiku-20241022",
    #    "output_max_token": 8192,
    #    "max_token": 200000,
    #    "input_price": 0.0008 / 1000,
    #    "output_price": 0.004 / 1000,
    #    "currency_code": "USD",
    #    "clsType": "LiteLLM2Chat",
    #},
    #"deepseek-chat": {
    #    "id": "deepseek/deepseek-chat",
    #    "output_max_token": 8192,
    #    "max_token": 64000,
    #    "input_price": 0.00014 / 1000,
    #    "output_price": 0.00028 / 1000,
    #    "currency_code": "USD",
    #    "clsType": "LiteLLM2Chat",
    #},
    #"deepseek-reasoner": {
    #    "id": "deepseek/deepseek-reasoner",
    #    "output_max_token": 8192,
    #    "max_token": 64000,
    #    "input_price": 0.00055 / 1000,
    #    "output_price": 0.00219 / 1000,
    #    "currency_code": "USD",
    #    "clsType": "LiteLLM2Chat",
    #},
    # LiteLLM Volcengine/Doubao models
    "doubao-1.5pro-32k": {
        "id": "doubao-1-5-pro-32k-250115",
        # Volcengine caps this endpoint's output at 16384; a higher value
        # 400s every request (VolcengineException: max_tokens above maximum).
        "output_max_token": 16384,
        "max_token": 100000,
        "input_price": 0.0008 / 1000,
        "output_price": 0.002 / 1000,
        "currency_code": "CNY",
        "provider": "volcengine",
        "timeout": 300,  # 5 minutes for long responses
        "async_limit": 30,  # max concurrent async API calls
        "clsType": "LiteLLM2Chat",
    },
    "doubao-1.5": {
        "id": "doubao-1-5-pro-32k-250115",
        # Volcengine caps this endpoint's output at 16384; a higher value
        # 400s every request (VolcengineException: max_tokens above maximum).
        "output_max_token": 16384,
        "max_token": 128000,
        "input_price": 0.0008 / 1000,
        "output_price": 0.002 / 1000,
        "currency_code": "CNY",
        "provider": "volcengine",
        "timeout": 300,  # 5 minutes for long responses
        "async_limit": 30,  # max concurrent async API calls
        "clsType": "LiteLLM2Chat",
    },
    "doubao-1.8": {
        "id": "doubao-seed-1-8-251228",
        "output_max_token": 32000,
        "max_token": 256000,
        "input_price": 0.0008 / 1000,
        "output_price": 0.002 / 1000,
        "currency_code": "CNY",
        "provider": "volcengine",
        "timeout": 300,
        "async_limit": 30,
        "completion_kwargs": {
            "reasoning_effort": "minimal",
            "allowed_openai_params": ["reasoning_effort"],
        },
        "clsType": "LiteLLM2Chat",
    },
    "doubao-2.0-lite": {
        "id": "doubao-seed-2-0-lite-260428",
        "output_max_token": 32000,
        "max_token": 256000,
        "input_price": 0.0006 / 1000,
        "output_price": 0.0036 / 1000,
        "currency_code": "CNY",
        "provider": "volcengine",
        "timeout": 300,
        "async_limit": 30,
        "completion_kwargs": {
            "reasoning_effort": "minimal",
            "allowed_openai_params": ["reasoning_effort"],
        },
        "clsType": "LiteLLM2Chat",
    },
    "doubao-2.0-mini": {
        "id": "doubao-seed-2-0-mini-260428",
         "output_max_token": 32000,
        "max_token": 256000,
        "input_price": 0.0002 / 1000,
        "output_price": 0.002 / 1000,
        "currency_code": "CNY",
        "provider": "volcengine",
        "timeout": 300,
        "async_limit": 30,
        "completion_kwargs": {
            "reasoning_effort": "minimal",
            "allowed_openai_params": ["reasoning_effort"],
        },
        "clsType": "LiteLLM2Chat",
    },
    "doubao-2.0-pro": {
        "id": "doubao-seed-2-0-pro-260215",
        "output_max_token": 32000,
        "max_token": 256000,
        "input_price": 0.0032 / 1000,
        "output_price": 0.016 / 1000,
        "currency_code": "CNY",
        "provider": "volcengine",
        "timeout": 300,
        "async_limit": 30,
        "completion_kwargs": {
            "reasoning_effort": "minimal",
            "allowed_openai_params": ["reasoning_effort"],
        },
        "clsType": "LiteLLM2Chat",
    },
    "deepseek-v4-pro": {
        "id": "deepseek-v4-pro-260425",
        "output_max_token": 32000,
        "max_token": 1024000,
        "input_price": 0.012 / 1000,
        "output_price": 0.024 / 1000,
        "currency_code": "CNY",
        "provider": "volcengine",
        "timeout": 300,
        "async_limit": 30,
        "completion_kwargs": {
            "reasoning_effort": "minimal",
            "allowed_openai_params": ["reasoning_effort"],
        },
        "clsType": "LiteLLM2Chat",
    },
    "deepseek-v4-lite": {
        "id": "deepseek-v4-flash-260425",
        "output_max_token": 32000,
        "max_token": 1024000,
        "input_price": 0.001 / 1000,
        "output_price": 0.002 / 1000,
        "currency_code": "CNY",
        "provider": "volcengine",
        "timeout": 300,
        "async_limit": 30,
        "completion_kwargs": {
            "reasoning_effort": "minimal",
            "allowed_openai_params": ["reasoning_effort"],
        },
        "clsType": "LiteLLM2Chat",
    },
    # Alias for the flash tier under its own name (same ARK endpoint id as
    # `deepseek-v4-lite`); this is the default model (settings.llm_default_model).
    "deepseek-v4-flash": {
        "id": "deepseek-v4-flash-260425",
        "output_max_token": 32000,
        "max_token": 1024000,
        "input_price": 0.001 / 1000,
        "output_price": 0.002 / 1000,
        "currency_code": "CNY",
        "provider": "volcengine",
        "timeout": 300,
        "async_limit": 30,
        "completion_kwargs": {
            "reasoning_effort": "minimal",
            "allowed_openai_params": ["reasoning_effort"],
        },
        "clsType": "LiteLLM2Chat",
    },
    # Same flash ARK endpoint, but reasoning_effort=medium — a distinct menu key
    # so its run slug (deepseek-v4-flash-medium) is a separate comparison run.
    "deepseek-v4-flash-medium": {
        "id": "deepseek-v4-flash-260425",
        "output_max_token": 32000,
        "max_token": 1024000,
        "input_price": 0.001 / 1000,
        "output_price": 0.002 / 1000,
        "currency_code": "CNY",
        "provider": "volcengine",
        "timeout": 300,
        "async_limit": 30,
        "completion_kwargs": {
            "reasoning_effort": "medium",
            "allowed_openai_params": ["reasoning_effort"],
        },
        "clsType": "LiteLLM2Chat",
    },
    # Same flash ARK endpoint, but reasoning_effort=high — distinct menu key so
    # its run slug (deepseek-v4-flash-high) is a separate comparison run.
    "deepseek-v4-flash-high": {
        "id": "deepseek-v4-flash-260425",
        "output_max_token": 32000,
        "max_token": 1024000,
        "input_price": 0.001 / 1000,
        "output_price": 0.002 / 1000,
        "currency_code": "CNY",
        "provider": "volcengine",
        "timeout": 300,
        "async_limit": 30,
        "completion_kwargs": {
            "reasoning_effort": "high",
            "allowed_openai_params": ["reasoning_effort"],
        },
        "clsType": "LiteLLM2Chat",
    },
    # Migrated from mxconfig `/projects/mxsieve$chatmodel.inner_extra`.
    # Keep in sync manually when Volcengine endpoints rotate.
    #'BI-doubao-1.5pro-32k': {'id': 'ep-20250828103330-vgx8p',
    #                         'output_max_token': 12288,
    #                         'max_token': 100000,
    #                         'input_price': 0.0000008,
    #                         'output_price': 0.0000002,
    #                         'currency_code': 'CNY',
    #                         'clsType': 'Volcengine2Chat'},
    #'doubao-seed-2.0-mini': {'id': 'ep-20260313140749-2b6wk',
    #                         'output_max_token': 16384,
    #                         'max_token': 256000,
    #                         'input_price': 0.0000008,
    #                         'output_price': 0.000008,
    #                         'currency_code': 'CNY',
    #                         'clsType': 'Volcengine2Chat'},
    #'doubao-seed-1.8': {'id': 'ep-20260330180324-td72x',
    #                    'output_max_token': 16384,
    #                    'max_token': 256000,
    #                    'input_price': 0.0000008,
    #                    'output_price': 0.000002,
    #                    'currency_code': 'CNY',
    #                    'clsType': 'Volcengine2Chat'},
    #'doubao-think': {'id': 'ep-20251127193714-565fs',
    #                 'output_max_token': 32000,
    #                 'max_token': 230000,
    #                 'input_price': 0.0008,
    #                 'output_price': 0.008,
    #                 'currency_code': 'CNY',
    #                 'clsType': 'Volcengine2Chat'},
}

# Active entries migrated from mxconfig `/projects/mxsieve$chatmodel.api_extra`.
# Historical entries below are commented for reference.
api_menus = {
    #'gpt-4.1': {'id': 'gpt-4.1',
    #            'output_max_token': 32768,
    #            'max_token': 1000000,
    #            'input_price': 0.000002,
    #            'output_price': 0.000008,
    #            'currency_code': 'USD',
    #            'clsType': 'OpenAi2Chat'},
    #'gpt-4.1-mini': {'id': 'gpt-4.1-mini',
    #                 'output_max_token': 32768,
    #                 'max_token': 1000000,
    #                 'input_price': 0.0000004,
    #                 'output_price': 0.0000016,
    #                 'currency_code': 'USD',
    #                 'clsType': 'OpenAi2Chat'},
    #'gpt-4.1-nano': {'id': 'gpt-4.1-nano',
    #                 'output_max_token': 32768,
    #                 'max_token': 1000000,
    #                 'input_price': 0.0000001,
    #                 'output_price': 0.00000025,
    #                 'currency_code': 'USD',
    #                 'clsType': 'OpenAi2Chat'},
    #'doubao-1.5pro-256k': {'id': 'ep-20251015165103-6v22l',
    #                       'output_max_token': 12288,
    #                       'max_token': 230000,
    #                       'input_price': 0.000005,
    #                       'output_price': 0.000009,
    #                       'currency_code': 'CNY',
    #                       'clsType': 'Volcengine2Chat'},
    # 'translation_doubao_32k': {'id': 'ep-20250109143227-t94ml',
    #                             'output_max_token': 4096,  # doubao 128k共用input和output
    #                             'max_token': 30000,
    #                             'input_price': 0.0008 / 1000,
    #                             'output_price': 0.002 / 1000,
    #                             'currency_code': 'CNY',
    #                             'clsType': 'Volcengine2Chat'},  # Volcengine doubao
    #
    # 'doubao-pro-32k': {'id': 'ep-20250213112627-7mmbv',
    #                     'output_max_token': 4096,  # doubao 128k共用input和output
    #                     'max_token': 30000,
    #                     'input_price': 0.0008 / 1000,
    #                     'output_price': 0.002 / 1000,
    #                     'currency_code': 'CNY',
    #                     'clsType': 'Volcengine2Chat'},  # Volcengine doubao
    #
    # 'deepseek-r1': {'id': 'ep-20250213112900-7q5sc',
    #                     'output_max_token': 8000,  # doubao 128k共用input和output
    #                     'max_token': 60000,
    #                     'input_price': 0.004 / 1000,
    #                     'output_price': 0.016 / 1000,
    #                     'currency_code': 'CNY',
    #                     'clsType': 'Volcengine2Chat'},  # Volcengine doubao
    #
    # 'doubao-1.5pro-32k': {'id': 'ep-20250522191202-rb7sw',
    #                       'output_max_token': 12288,  # doubao 共用input和output
    #                       'max_token': 100000,
    #                       'input_price': 0.0008 / 1000,
    #                       'output_price': 0.0002 / 1000,
    #                       'currency_code': 'CNY',
    #                       'clsType': 'Volcengine2Chat'},  # Volcengine doubao
    #
    # 'doubao-seed-1.6-think': {'id': 'ep-20250730112507-6w7dr',
    #                           'output_max_token': 32768,  # doubao 共用input和output
    #                           'max_token': 224000,
    #                           'input_price': 0.0008 / 1000,
    #                           'output_price': 0.008 / 1000,
    #                           'currency_code': 'CNY',
    #                           'clsType': 'Volcengine2Chat'},  # Volcengine doubao
}
