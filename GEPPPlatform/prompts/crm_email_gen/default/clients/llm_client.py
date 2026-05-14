"""
LLM Client for CRM Email Generation.

Uses OpenRouter's OpenAI-compatible REST API via stdlib `urllib` — no `openai`
SDK dependency required. The Lambda deployment package would otherwise need
~25MB of openai+pydantic for one HTTP POST.

Public API:
    call_llm_for_email(prompt, tone, variables) -> {
        subject, body_html, body_plain, variables_detected, model, token_usage
    }

Wire-compatible with the previous openai-SDK version — same kwargs, same
return shape. See prompts/ai_audit_v1/default/clients/llm_client.py for the
older pattern (which still uses the SDK because it's in a different Lambda).
"""

import os
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

logger = logging.getLogger(__name__)

SETTINGS_PATH = Path(__file__).parent.parent / 'settings.json'
OPENROUTER_URL = 'https://openrouter.ai/api/v1/chat/completions'

_cached_settings: Optional[Dict[str, Any]] = None
_cached_settings_mtime: float = 0


def _load_settings() -> Dict[str, Any]:
    """Load settings from settings.json (cached by mtime)."""
    global _cached_settings, _cached_settings_mtime
    try:
        mtime = SETTINGS_PATH.stat().st_mtime
    except OSError:
        mtime = 0
    if _cached_settings is None or mtime != _cached_settings_mtime:
        with open(SETTINGS_PATH, 'r') as f:
            _cached_settings = json.load(f)
        _cached_settings_mtime = mtime
    return _cached_settings


def _post_chat_completion(
    api_key: str,
    payload: Dict[str, Any],
    timeout: int = 60,
) -> Dict[str, Any]:
    """POST to OpenRouter chat/completions. Returns parsed JSON dict."""
    req = Request(
        OPENROUTER_URL,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            # OpenRouter best practice — identifies the calling app for their
            # dashboard. Optional but they recommend setting it.
            'HTTP-Referer': os.environ.get('OPENROUTER_REFERER', 'https://gepp.me'),
            'X-Title': 'GEPP CRM Email Generation',
        },
        method='POST',
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode('utf-8')
    except HTTPError as e:
        # Surface the body for actionable error messages (401, 402, 429, etc.)
        try:
            body = e.read().decode('utf-8')
        except Exception:
            body = ''
        raise RuntimeError(f"OpenRouter HTTP {e.code}: {body or e.reason}") from e
    except URLError as e:
        raise RuntimeError(f"OpenRouter network error: {e.reason}") from e

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"OpenRouter returned non-JSON response: {raw[:200]}") from e


def call_llm_for_email(
    prompt: str,
    tone: str = 'professional',
    variables: Optional[List[str]] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a CRM email from a natural-language prompt.

    Args:
        prompt:     Natural-language description of the email goal,
                    e.g. "Win them back with 100 bonus points".
        tone:       Desired writing tone: 'professional', 'friendly', 'urgent', etc.
        variables:  List of template variable names that should appear in the output,
                    e.g. ['{{user.name}}', '{{reward_points}}'].
                    Hints (not enforced) — the LLM decides what makes sense.
        model:      Model override; defaults to settings.json value.

    Returns:
        {
            "subject":            str,
            "body_html":          str,
            "body_plain":         str,
            "variables_detected": list,
            "model":              str,
            "token_usage":        {"input_tokens": int, "output_tokens": int}
        }

    Raises:
        ValueError:  if OPENROUTER_API_KEY is not set.
        RuntimeError: on transport / parse errors (caught by handler as 400).
    """
    from ..scripts.generate_email import build_prompt, parse_response

    api_key = os.environ.get('OPENROUTER_API_KEY')
    if not api_key:
        raise ValueError('OPENROUTER_API_KEY environment variable not set')

    settings = _load_settings()
    resolved_model = model or settings.get('model', 'google/gemini-3-flash-preview')

    system_prompt, user_prompt = build_prompt(prompt, tone, variables or [])

    payload = {
        "model": resolved_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "temperature": settings.get('temperature', 0.7),
        "max_tokens":  settings.get('max_tokens', 2000),
    }

    try:
        response = _post_chat_completion(api_key, payload)
    except Exception as e:
        logger.error("call_llm_for_email transport failed: %s", e)
        raise

    # OpenAI-compatible response: choices[0].message.content + usage{prompt_tokens, completion_tokens}
    choices = response.get('choices') or []
    if not choices:
        raise RuntimeError(f"OpenRouter response has no choices: {str(response)[:200]}")
    content = (choices[0].get('message') or {}).get('content') or ''

    usage_obj = response.get('usage') or {}
    usage = {
        "input_tokens":  int(usage_obj.get('prompt_tokens')     or 0),
        "output_tokens": int(usage_obj.get('completion_tokens') or 0),
    }

    parsed = parse_response(content)

    return {
        "subject":            parsed.get("subject", ""),
        "body_html":          parsed.get("body_html", ""),
        "body_plain":         parsed.get("body_plain", ""),
        "variables_detected": parsed.get("variables_detected", []),
        "model":              resolved_model,
        "token_usage":        usage,
    }
