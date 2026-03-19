"""
ESG Classification LLM Client
Reuses OpenRouter infrastructure from ai_audit_v1, with ESG-specific prompts
"""

import json
import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Settings cache
_settings = None
_settings_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'settings.json')


def _get_settings() -> Dict[str, Any]:
    """Load settings from settings.json"""
    global _settings
    if _settings is None:
        with open(_settings_path, 'r') as f:
            _settings = json.load(f)
    return _settings


def _get_llm_client():
    """Get OpenRouter LLM client (OpenAI-compatible)"""
    from openai import OpenAI

    api_key = os.environ.get('OPENROUTER_API_KEY')
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY environment variable is required")

    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )


def _call_llm_with_images(prompt: str, image_urls: list, settings: Dict = None) -> Dict[str, Any]:
    """Call LLM with text prompt and image URLs"""
    if settings is None:
        settings = _get_settings()

    client = _get_llm_client()

    content = [{"type": "text", "text": prompt}]
    for url in image_urls:
        if url.startswith('s3://'):
            # Generate presigned URL for S3
            url = _get_s3_presigned_url(url)
        content.append({
            "type": "image_url",
            "image_url": {"url": url}
        })

    response = client.chat.completions.create(
        model=settings.get('model', 'google/gemini-3-flash-preview'),
        messages=[{"role": "user", "content": content}],
        temperature=settings.get('temperature', 0.1),
        max_tokens=settings.get('max_tokens', 4096),
    )

    return {
        'content': response.choices[0].message.content,
        'usage': {
            'input_tokens': response.usage.prompt_tokens if response.usage else 0,
            'output_tokens': response.usage.completion_tokens if response.usage else 0,
        }
    }


def _call_llm_text_only(prompt: str, settings: Dict = None) -> Dict[str, Any]:
    """Call LLM with text-only prompt"""
    if settings is None:
        settings = _get_settings()

    client = _get_llm_client()

    response = client.chat.completions.create(
        model=settings.get('model', 'google/gemini-3-flash-preview'),
        messages=[{"role": "user", "content": prompt}],
        temperature=settings.get('temperature', 0.1),
        max_tokens=settings.get('max_tokens', 4096),
    )

    return {
        'content': response.choices[0].message.content,
        'usage': {
            'input_tokens': response.usage.prompt_tokens if response.usage else 0,
            'output_tokens': response.usage.completion_tokens if response.usage else 0,
        }
    }


def _parse_json_response(text: str) -> Optional[Dict]:
    """Parse JSON from LLM response, handling markdown fences"""
    if not text:
        return None

    # Strip markdown code fences
    cleaned = text.strip()
    if cleaned.startswith('```json'):
        cleaned = cleaned[7:]
    elif cleaned.startswith('```'):
        cleaned = cleaned[3:]
    if cleaned.endswith('```'):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find first JSON object
        start = cleaned.find('{')
        if start >= 0:
            depth = 0
            for i, c in enumerate(cleaned[start:], start):
                if c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(cleaned[start:i+1])
                        except json.JSONDecodeError:
                            break
    return None


def _get_s3_presigned_url(s3_url: str, expiration: int = 3600) -> str:
    """Generate a presigned URL for an S3 object"""
    import boto3

    # Parse s3://bucket/key
    parts = s3_url.replace('s3://', '').split('/', 1)
    bucket = parts[0]
    key = parts[1] if len(parts) > 1 else ''

    s3_client = boto3.client('s3')
    url = s3_client.generate_presigned_url(
        'get_object',
        Params={'Bucket': bucket, 'Key': key},
        ExpiresIn=expiration
    )
    return url


# ============================================================
# Public API Functions
# ============================================================

ESG_CLASSIFY_PROMPT = """You are an ESG (Environment, Social, Governance) document classifier.
Analyze the document image and classify it into the ESG framework.

Respond in JSON format with these fields:
{
    "esg_category": "environment" | "social" | "governance",
    "esg_subcategory": "<specific subcategory>",
    "document_type": "<type of document>",
    "document_date": "<YYYY-MM-DD or null>",
    "vendor_name": "<vendor/company name or null>",
    "summary": "<brief 1-2 sentence summary>",
    "tags": ["<relevant tags>"],
    "confidence": <0.0 to 1.0>
}

ESG Subcategories:
- Environment: scope1_emissions, scope2_emissions, scope3_waste, scope3_transport, energy, water, biodiversity, pollution
- Social: labor_practices, health_safety, human_rights, community, diversity, training, supply_chain_social
- Governance: board_diversity, anti_corruption, risk_management, compliance, ethics, transparency, data_privacy

Document Types:
- waste_manifest, weighbridge_ticket, invoice, receipt, certificate, license
- policy, procedure, report, audit_report, assessment, training_record
- meeting_minutes, board_resolution, compliance_report, other

Analyze the document carefully. If it's a waste-related document (weighbridge ticket, waste manifest, recycling receipt),
classify as environment/scope3_waste. Extract vendor name and date if visible.
"""

WASTE_EXTRACT_PROMPT = """You are a waste data extraction specialist.
Analyze this waste-related document and extract structured waste data.

Respond in JSON format:
{
    "waste_items": [
        {
            "waste_type": "general" | "organic" | "plastic" | "paper" | "glass" | "metal" | "electronic" | "hazardous",
            "waste_category": "municipal_solid" | "industrial" | "construction" | null,
            "treatment_method": "landfill" | "incineration" | "recycling" | "composting" | "anaerobic_digestion",
            "weight_kg": <number>,
            "cost": <number or null>,
            "record_date": "<YYYY-MM-DD>",
            "vendor_name": "<name or null>",
            "notes": "<any additional details>"
        }
    ],
    "document_total_weight_kg": <total or null>,
    "document_total_cost": <total or null>
}

Rules:
- Extract ALL waste items mentioned in the document
- Convert all weights to kg (1 ton = 1000 kg)
- If treatment method is not specified, infer from context (recycling center → recycling, landfill site → landfill)
- If waste type is unclear, use "general"
- Date should be the transaction/service date, not the document print date
"""


def classify_esg_document(file_url: str, file_name: str) -> Optional[Dict[str, Any]]:
    """
    Step 1: Classify an ESG document using AI
    Returns classification result dict
    """
    try:
        result = _call_llm_with_images(ESG_CLASSIFY_PROMPT, [file_url])
        parsed = _parse_json_response(result['content'])

        if parsed:
            logger.info(f"ESG classification for {file_name}: {parsed.get('esg_category')}/{parsed.get('esg_subcategory')}")
            return parsed

        logger.warning(f"Failed to parse classification result for {file_name}")
        return None

    except Exception as e:
        logger.error(f"ESG classification error for {file_name}: {str(e)}")
        raise


def extract_waste_data(file_url: str, file_name: str) -> Optional[Dict[str, Any]]:
    """
    Step 2: Extract waste data from waste-related documents
    Returns dict with waste_items list
    """
    try:
        result = _call_llm_with_images(WASTE_EXTRACT_PROMPT, [file_url])
        parsed = _parse_json_response(result['content'])

        if parsed and parsed.get('waste_items'):
            logger.info(f"Extracted {len(parsed['waste_items'])} waste items from {file_name}")
            return parsed

        logger.warning(f"No waste items extracted from {file_name}")
        return None

    except Exception as e:
        logger.error(f"Waste extraction error for {file_name}: {str(e)}")
        raise
