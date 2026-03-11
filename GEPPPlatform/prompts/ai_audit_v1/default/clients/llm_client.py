"""
LLM Client for Default AI Audit
Uses OpenRouter API via langchain-openai ChatOpenAI
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)

SETTINGS_PATH = Path(__file__).parent / 'settings.json'


def _load_settings() -> Dict[str, Any]:
    """Load settings from settings.json"""
    with open(SETTINGS_PATH, 'r') as f:
        return json.load(f)


def get_default_audit_llm(model: str = None) -> ChatOpenAI:
    """
    Create ChatOpenAI instance pointing to OpenRouter.

    Args:
        model: Model identifier override. Defaults to settings.json value.

    Returns:
        ChatOpenAI configured for OpenRouter
    """
    settings = _load_settings()
    api_key = os.environ.get('OPENROUTER_API_KEY')
    if not api_key:
        raise ValueError('OPENROUTER_API_KEY environment variable not set')

    return ChatOpenAI(
        model=model or settings.get('model', 'x-ai/grok-4.1-fast'),
        openai_api_key=api_key,
        openai_api_base='https://openrouter.ai/api/v1',
        temperature=settings.get('temperature', 0.1),
        max_tokens=settings.get('max_tokens', 4096),
    )


def call_llm_with_images(
    llm: ChatOpenAI,
    text_prompt: str,
    image_urls: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Send a multimodal prompt (text + images) to the LLM.

    Args:
        llm: ChatOpenAI instance
        text_prompt: Text prompt content
        image_urls: Optional list of image URLs (presigned S3 URLs)

    Returns:
        dict with keys: content (str), usage (dict with input_tokens, output_tokens)
    """
    content_parts = [{"type": "text", "text": text_prompt}]

    if image_urls:
        for url in image_urls:
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": url}
            })

    message = HumanMessage(content=content_parts)

    try:
        response = llm.invoke([message])
        usage = {}
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            usage = {
                'input_tokens': getattr(response.usage_metadata, 'input_tokens', 0),
                'output_tokens': getattr(response.usage_metadata, 'output_tokens', 0),
            }
        elif hasattr(response, 'response_metadata'):
            token_usage = response.response_metadata.get('token_usage', {})
            usage = {
                'input_tokens': token_usage.get('prompt_tokens', 0),
                'output_tokens': token_usage.get('completion_tokens', 0),
            }

        return {
            'content': response.content.strip(),
            'usage': usage,
        }
    except Exception as e:
        logger.error(f"LLM call failed: {str(e)}")
        raise


def call_llm_text_only(
    llm: ChatOpenAI,
    text_prompt: str
) -> Dict[str, Any]:
    """
    Send a text-only prompt to the LLM.

    Args:
        llm: ChatOpenAI instance
        text_prompt: Text prompt content

    Returns:
        dict with keys: content (str), usage (dict with input_tokens, output_tokens)
    """
    return call_llm_with_images(llm, text_prompt, image_urls=None)


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
