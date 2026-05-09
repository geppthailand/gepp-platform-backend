"""
OpenRouter chat client for KhunGEPP.

Mirrors the wrapper shape used by `prompts/esg_classify/clients/llm_client.py`
(OpenAI-compatible client pointed at https://openrouter.ai/api/v1)
but switches the default model to `deepseek/deepseek-v4-flash` per
product direction — DeepSeek is faster + cheaper for short Thai
chat turns and the Gemini path is reserved for image extraction.

Settings (model / temperature / max_tokens) are loaded from the
sibling `settings.json` and cached, with mtime-based invalidation
so a deploy-time edit takes effect without a process restart.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_SETTINGS_PATH = Path(__file__).parent.parent / 'settings.json'

# Cache + mtime guard so a deploy-time settings.json edit propagates
# on the next call without restarting the worker.
_settings_cache: Optional[Dict[str, Any]] = None
_settings_mtime: Optional[float] = None

# Hard upper bound on a single chat completion. LINE replies are
# atomic — if OpenRouter is slow we'd rather show the user a
# graceful fallback than have the webhook stall and timeout. 12s
# is comfortably above DeepSeek-V4-Flash's median (~2-4s) but tight
# enough that a stuck inference fails fast.
_REQUEST_TIMEOUT_SECONDS = 12


def _get_settings() -> Dict[str, Any]:
    global _settings_cache, _settings_mtime
    try:
        mtime = _SETTINGS_PATH.stat().st_mtime
    except OSError:
        # File missing — fall back to in-memory defaults so dev still works.
        return {
            'model': 'google/gemini-3-flash-preview',
            'temperature': 0.6,
            'max_tokens': 220,
        }
    if _settings_cache is None or mtime != _settings_mtime:
        with open(_SETTINGS_PATH, 'r', encoding='utf-8') as fh:
            _settings_cache = json.load(fh)
        _settings_mtime = mtime
    return _settings_cache


def _get_chat_client():
    """OpenAI-compatible client pointed at OpenRouter, with a hard
    per-request timeout so a stalled inference can't hang LINE."""
    from openai import OpenAI

    api_key = os.environ.get('OPENROUTER_API_KEY')
    if not api_key:
        raise ValueError('OPENROUTER_API_KEY environment variable is required')
    return OpenAI(
        base_url='https://openrouter.ai/api/v1',
        api_key=api_key,
        timeout=_REQUEST_TIMEOUT_SECONDS,
    )


def chat_complete(messages: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Send a multi-turn chat completion through OpenRouter.

    `messages` follows the OpenAI shape:
        [{'role': 'system'|'user'|'assistant', 'content': '...'}]

    Returns:
        {
          'content': str,        # the assistant's reply text
          'model': str,          # the model id we used (echo from settings)
          'usage': {
            'prompt_tokens': int|None,
            'completion_tokens': int|None,
          },
        }

    Raises on auth / network / model errors — the caller wraps with a
    fallback message so users still see a graceful reply.
    """
    settings = _get_settings()
    client = _get_chat_client()

    response = client.chat.completions.create(
        model=settings.get('model', 'google/gemini-3-flash-preview'),
        messages=messages,
        temperature=settings.get('temperature', 0.6),
        max_tokens=settings.get('max_tokens', 220),
    )

    choice = response.choices[0].message
    usage = getattr(response, 'usage', None)
    return {
        'content': (choice.content or '').strip(),
        'model': settings.get('model', 'google/gemini-3-flash-preview'),
        'usage': {
            'prompt_tokens': getattr(usage, 'prompt_tokens', None) if usage else None,
            'completion_tokens': getattr(usage, 'completion_tokens', None) if usage else None,
        },
    }
