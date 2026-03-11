"""
LLM Client for Default AI Audit
Uses OpenRouter API via the openai Python package (OpenAI-compatible API)
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)

SETTINGS_PATH = Path(__file__).parent.parent / 'settings.json'


def _load_settings() -> Dict[str, Any]:
    """Load settings from settings.json"""
    with open(SETTINGS_PATH, 'r') as f:
        return json.load(f)


def get_default_audit_llm() -> OpenAI:
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


def call_llm_with_images(
    client: OpenAI,
    text_prompt: str,
    image_urls: Optional[List[str]] = None,
    model: str = None,
) -> Dict[str, Any]:
    """
    Send a multimodal prompt (text + images) to the LLM.

    Args:
        client: OpenAI client instance
        text_prompt: Text prompt content
        image_urls: Optional list of image URLs (presigned S3 URLs)
        model: Model override. Defaults to settings.json value.

    Returns:
        dict with keys: content (str), usage (dict with input_tokens, output_tokens)
    """
    settings = _load_settings()
    model = model or settings.get('model', 'x-ai/grok-4.1-fast')

    content_parts = [{"type": "text", "text": text_prompt}]

    if image_urls:
        for url in image_urls:
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": url}
            })

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": content_parts}],
            temperature=settings.get('temperature', 0.1),
            max_tokens=settings.get('max_tokens', 4096),
        )

        usage = {}
        if response.usage:
            usage = {
                'input_tokens': response.usage.prompt_tokens or 0,
                'output_tokens': response.usage.completion_tokens or 0,
            }

        return {
            'content': response.choices[0].message.content.strip(),
            'usage': usage,
        }
    except Exception as e:
        logger.error(f"LLM call failed: {str(e)}")
        raise


def call_llm_text_only(
    client: OpenAI,
    text_prompt: str,
    model: str = None,
) -> Dict[str, Any]:
    """
    Send a text-only prompt to the LLM.

    Args:
        client: OpenAI client instance
        text_prompt: Text prompt content
        model: Model override.

    Returns:
        dict with keys: content (str), usage (dict with input_tokens, output_tokens)
    """
    return call_llm_with_images(client, text_prompt, image_urls=None, model=model)


def parse_json_response(response_text: str) -> Dict[str, Any]:
    """
    Parse JSON from LLM response, stripping markdown fences if present.

    Args:
        response_text: Raw LLM response text

    Returns:
        Parsed JSON dict
    """
    text = response_text.strip()

    # Strip markdown code fences
    if text.startswith('```'):
        lines = text.split('\n')
        # Remove first line (```json or ```)
        lines = lines[1:]
        # Remove last line (```)
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        text = '\n'.join(lines).strip()

    return json.loads(text)
