"""
LLM Client for CRM Email Generation
Uses OpenRouter API via the openai Python package (OpenAI-compatible API).

Pattern copied exactly from prompts/ai_audit_v1/default/clients/llm_client.py.
Same OPENROUTER_API_KEY env var, same settings.json loading/caching approach.

Public API:
    call_llm_for_email(prompt, tone, variables) -> {
        subject, body_html, body_plain, variables_detected, model, token_usage
    }
"""

import os
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)

SETTINGS_PATH = Path(__file__).parent.parent / 'settings.json'


_cached_settings = None
_cached_settings_mtime = 0


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


def get_email_gen_llm() -> OpenAI:
    """
    Create OpenAI client pointing to OpenRouter.

    Returns:
        OpenAI client configured for OpenRouter
    """
    api_key = os.environ.get('OPENROUTER_API_KEY')
    if not api_key:
        raise ValueError('OPENROUTER_API_KEY environment variable not set')

    return OpenAI(
        api_key=api_key,
        base_url='https://openrouter.ai/api/v1',
    )


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
            "subject":            str,   # Email subject line
            "body_html":          str,   # Inline-styled HTML body
            "body_plain":         str,   # Plain-text version
            "variables_detected": list,  # Variable placeholders the LLM used
            "model":              str,   # Model that generated the content
            "token_usage":        {      # Raw token counts from the API
                "input_tokens":  int,
                "output_tokens": int,
            }
        }

    Raises:
        ValueError:  if OPENROUTER_API_KEY is not set.
        Exception:   propagates LLM or JSON-parse errors to the caller.
    """
    from ..scripts.generate_email import build_prompt, parse_response

    settings = _load_settings()
    resolved_model = model or settings.get('model', 'google/gemini-3-flash-preview')

    client = get_email_gen_llm()

    system_prompt, user_prompt = build_prompt(prompt, tone, variables or [])

    try:
        response = client.chat.completions.create(
            model=resolved_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=settings.get('temperature', 0.7),
            max_tokens=settings.get('max_tokens', 2000),
        )

        content = response.choices[0].message.content or ""

        usage = {}
        if response.usage:
            usage = {
                "input_tokens":  response.usage.prompt_tokens or 0,
                "output_tokens": response.usage.completion_tokens or 0,
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

    except Exception as e:
        logger.error("call_llm_for_email failed: %s", e)
        raise
