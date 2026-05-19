"""
CRM Email Generation — prompt builder + LLM response parser.

Builds a system + user prompt from input parameters and parses the JSON
response returned by the LLM back into a structured dict.

Available template variable placeholders (mentioned in system prompt):
    {{user.name}}              {{user.email}}             {{user.first_name}}
    {{org.name}}               {{last_login_date}}        {{days_since_last_login}}
    {{transaction_count_30d}}  {{reward_points}}          {{next_payment_date}}
    {{unsubscribe_url}}        {{ custom.<key> }}
"""

import json
import logging
import re
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Available variable placeholders documented for the LLM
# ---------------------------------------------------------------------------

_VARIABLE_DOCS = """\
Available variable placeholders you MAY include (use exactly as written):
  {{user.name}}             — recipient's full name
  {{user.first_name}}       — recipient's first name
  {{user.email}}            — recipient's email address
  {{org.name}}              — organisation name
  {{last_login_date}}       — date of last platform login
  {{days_since_last_login}} — number of days since last login
  {{transaction_count_30d}} — number of transactions in last 30 days
  {{reward_points}}         — current reward points balance
  {{next_payment_date}}     — next subscription payment date
  {{unsubscribe_url}}       — unsubscribe link (always include in body)
  {{ custom.<key> }}        — any custom variable (replace <key> with a descriptive name)
"""


def build_prompt(
    prompt: str,
    tone: str,
    variables: List[str],
) -> Tuple[str, str]:
    """
    Build (system_prompt, user_prompt) for the LLM.

    Args:
        prompt:    Natural-language email goal from the admin.
        tone:      Writing tone (e.g. 'professional', 'friendly', 'urgent').
        variables: Suggested variables to use (may be empty).

    Returns:
        (system_prompt, user_prompt)
    """
    variable_hint = ""
    if variables:
        variable_hint = (
            f"\n\nThe user has suggested including these variable placeholders: "
            f"{', '.join(variables)}. Use them where they make sense."
        )

    system_prompt = f"""\
You are an expert CRM email copywriter for a sustainability and ESG data platform called GEPP.

Your task is to write a compelling marketing email based on the user's brief.

STRICT OUTPUT FORMAT — you MUST respond with ONLY a single valid JSON object (no markdown fences, no extra text):
{{
  "subject": "<email subject line>",
  "body_html": "<complete HTML email body with simple inline styles>",
  "body_plain": "<plain-text version of the same email>",
  "variables_detected": ["{{user.name}}", "{{unsubscribe_url}}", ...]
}}

HTML guidelines:
- Use simple inline CSS only (no <style> blocks, no external CSS).
- Keep the structure clean: a single-column layout with a maximum width of 600px.
- Use a professional color palette (white background, dark text, one accent color).
- Always include an unsubscribe link using {{{{unsubscribe_url}}}}.

Plain-text guidelines:
- Mirror the HTML content as readable plain text.
- Include the unsubscribe URL literally: {{{{unsubscribe_url}}}}.

Writing tone: {tone}

{_VARIABLE_DOCS}

"variables_detected" must list every variable placeholder (including custom.*) that appears in your output.
"""

    user_prompt = f"Email goal: {prompt}{variable_hint}"

    return system_prompt, user_prompt


def parse_response(raw_content: str) -> Dict[str, Any]:
    """
    Parse the LLM JSON response into a structured dict.

    Handles markdown code fences and attempts to extract a JSON object if the
    model returns extra prose around the JSON.

    Args:
        raw_content: Raw text from the LLM.

    Returns:
        Dict with keys: subject, body_html, body_plain, variables_detected.

    Raises:
        ValueError: if no valid JSON can be extracted.
    """
    text = (raw_content or "").strip()

    # Strip markdown code fences (```json ... ``` or ``` ... ```)
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]  # drop opening fence line
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # Attempt direct parse
    try:
        parsed = json.loads(text)
        return _validate_parsed(parsed)
    except json.JSONDecodeError:
        pass

    # Fallback: extract first complete JSON object from the string
    start = text.find("{")
    if start == -1:
        raise ValueError("LLM response contains no JSON object.")

    depth = 0
    in_string = False
    escape_next = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    parsed = json.loads(text[start : i + 1])
                    return _validate_parsed(parsed)
                except json.JSONDecodeError:
                    break

    raise ValueError(
        f"Could not parse a valid JSON object from LLM response. "
        f"Raw content (first 500 chars): {raw_content[:500]}"
    )


def _validate_parsed(parsed: Any) -> Dict[str, Any]:
    """
    Ensure the parsed dict has required keys; fill defaults for optional ones.
    """
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected JSON object, got {type(parsed).__name__}.")

    # Ensure required fields are present (even if empty strings)
    for key in ("subject", "body_html", "body_plain"):
        if key not in parsed:
            logger.warning("generate_email: LLM response missing key '%s'; defaulting to ''", key)
            parsed[key] = ""

    if "variables_detected" not in parsed or not isinstance(parsed["variables_detected"], list):
        # Auto-detect from body_html as fallback
        var_pattern = re.compile(r'\{\{\s*[^}]+\s*\}\}')
        detected = list(set(var_pattern.findall(parsed.get("body_html", ""))))
        parsed["variables_detected"] = detected

    return parsed
