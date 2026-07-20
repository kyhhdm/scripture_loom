# -*- coding: utf-8 -*-
from .menu import inner_menu, api_menus, _CLASS_MODULES
import logging
import importlib

logger = logging.getLogger(__name__)

# Cache for lazily loaded classes
_class_cache = {}


def _resolve_class(cls_name: str):
    """Lazily import and return model class.

    This allows using models without requiring all dependencies upfront.
    For example, using LiteLLM doesn't require boto3 (needed for BedRock).
    """
    if cls_name in _class_cache:
        return _class_cache[cls_name]

    module_path = _CLASS_MODULES.get(cls_name)
    if not module_path:
        raise ValueError(f"Unknown model class: {cls_name}")

    module = importlib.import_module(module_path, package='llm_core.chatmodels')
    cls = getattr(module, cls_name)
    _class_cache[cls_name] = cls
    return cls

def check_modelId(modelId) -> str:
    if modelId in {None, "None", ""}:
        return None
    else:
        return modelId

def model_illegal(modelId, format_type='api'):
    if format_type == "api":
        if modelId in api_menus:
            return api_menus
    elif format_type == 'inner':
        if modelId in inner_menu:
            return inner_menu
    else:
        return


def valid_model_ids(format_type='inner') -> set:
    """Return the set of registered model names for the given menu.

    Single source of truth for "does this model exist" checks — reuse this
    instead of re-implementing menu membership at call sites.
    """
    return set(inner_menu if format_type == 'inner' else api_menus)


def list_models(format_type='inner') -> list:
    """Public, schema-stable view of registered chat models.

    Returns one dict per model with only the caller-relevant fields; internal
    plumbing (``clsType``, raw endpoint id) is intentionally omitted. ``name``
    is the value to pass as ``llm_model``.
    """
    menu = inner_menu if format_type == 'inner' else api_menus
    return [
        {
            "name": name,
            "provider": m.get("provider", "litellm"),
            "max_token": m.get("max_token"),
            "output_max_token": m.get("output_max_token"),
            "input_price": m.get("input_price"),
            "output_price": m.get("output_price"),
            "currency_code": m.get("currency_code"),
        }
        for name, m in menu.items()
    ]

def build_chat(modelId, 
               format_type='inner',
               **kwargs) -> [object, str]:
    
    modelId = check_modelId(modelId)
    if modelId is None:
        return None, f"ModelId:{modelId} illegal!"

    ModelIdMenu = model_illegal(modelId, format_type)

    if ModelIdMenu is None:
        return None, f"ModelId:{modelId} illegal!"

    model_args= ModelIdMenu.get(modelId)
    logger.info(f'build_chat chat_model={modelId}, other args:{kwargs}')

    # Build optional parameters dict
    optional_params = {}
    if 'output_max_token' in model_args:
        optional_params['output_max_token'] = model_args['output_max_token']
    if 'provider' in model_args:
        optional_params['provider'] = model_args['provider']
    if 'timeout' in model_args:
        optional_params['timeout'] = model_args['timeout']
    if 'async_limit' in model_args:
        optional_params['async_limit'] = model_args['async_limit']
    if 'llm_debug' in model_args:
        optional_params['llm_debug'] = model_args['llm_debug']
    if 'use_history' in model_args:
        optional_params['use_history'] = model_args['use_history']
    if 'completion_kwargs' in model_args:
        optional_params['completion_kwargs'] = model_args['completion_kwargs']

    # Resolve string class name to actual class (lazy import)
    cls_type = model_args['clsType']
    if isinstance(cls_type, str):
        cls_type = _resolve_class(cls_type)

    return cls_type(**{**kwargs,
                                    **{'modelId': model_args['id'],
                                       'max_token': model_args['max_token'],
                                       'input_price': model_args['input_price'],
                                       'output_price': model_args['output_price'],
                                       'currency_code': model_args['currency_code']
                                       },
                                    **optional_params
                                    }
                                 ), ''

