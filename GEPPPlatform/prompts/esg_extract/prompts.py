"""
ESG Cascade Extraction Prompt Templates.

Used by EsgExtractionService for the 3-step cascade:
  1. Category classification
  2. Subcategory classification
  3. Datapoint extraction

These prompts come in two flavours:

  *_PROMPT          — original full-ESG prompt (E + S + G), kept for the
                      'full_esg' focus mode and never deleted.
  *_PROMPT_SCOPE3   — narrowed Carbon Scope 3 prompt. Used when the
                      organization's `focus_mode` is 'scope3_only' (the
                      default). The model is explicitly instructed that
                      it MUST return `no_match` for inputs that don't
                      fit Scope 3 — it must NOT classify into Social,
                      Governance, Scope 1 or Scope 2 even when the input
                      mentions them.

The active prompt for any extraction is selected at request time by
EsgExtractionService based on the org's focus_mode setting.

The smaller taxonomy is also expected to *reduce false-positive
classifications* because the LLM no longer chooses between 100+
subcategories across three pillars.
"""

# ─── ORIGINAL FULL-ESG PROMPTS (preserved for focus_mode='full_esg') ────────

CATEGORY_CLASSIFY_PROMPT = """You are an ESG (Environmental, Social, Governance) data classifier.
Analyze the following input and determine which ESG data categories it relates to.
One input can match multiple categories.

Available categories:
{categories_json}

Input to analyze:
{input_content}

Respond in JSON format ONLY:
{{
    "matches": [
        {{
            "category_id": <int>,
            "category_name": "<name>",
            "confidence": <0.0-1.0>,
            "reasoning": "<brief explanation>"
        }}
    ]
}}

Rules:
- Include ALL categories that the input could relate to
- Minimum confidence threshold: 0.3
- If the input is not related to any ESG category, return empty matches
- Be thorough - a single receipt or document may relate to multiple categories
"""

SUBCATEGORY_CLASSIFY_PROMPT = """You are an ESG data classifier performing subcategory matching.
Given the input and the matched category, identify which subcategories the input relates to.

Category: {category_name}
Available subcategories:
{subcategories_json}

Input to analyze:
{input_content}

Respond in JSON format ONLY:
{{
    "matches": [
        {{
            "subcategory_id": <int>,
            "subcategory_name": "<name>",
            "confidence": <0.0-1.0>,
            "reasoning": "<brief explanation>"
        }}
    ]
}}

Rules:
- Include ALL subcategories that the input could satisfy
- Minimum confidence threshold: 0.3
- Consider that one document (e.g., a receipt) may relate to multiple subcategories
"""

DATAPOINT_EXTRACT_PROMPT = """You are an ESG data extraction specialist.
Extract specific data point values from the input based on the available datapoints.

Subcategory: {subcategory_name}
Available datapoints to extract:
{datapoints_json}

Input to analyze:
{input_content}

Respond in JSON format ONLY:
{{
    "matches": [
        {{
            "datapoint_id": <int>,
            "datapoint_name": "<name>",
            "value": <extracted value - number, string, or date as appropriate>,
            "unit": "<unit if applicable>",
            "confidence": <0.0-1.0>
        }}
    ],
    "refs": {{
        "document_date": "<YYYY-MM-DD or null>",
        "vendor": "<vendor/company name or null>",
        "location": "<location or null>",
        "reference_number": "<invoice/receipt/manifest number or null>"
    }}
}}

Rules:
- Extract ALL datapoints that can be found in the input
- Convert values to the expected unit (e.g., tons to kg)
- If a value is mentioned but uncertain, include it with lower confidence
- Extract reference information (date, vendor, location) when available
- For text data_type datapoints, extract the text value
- For numeric data_type datapoints, extract the number only
- For date data_type datapoints, extract in YYYY-MM-DD format
"""


# ─── SCOPE-3-ONLY PROMPTS (active when focus_mode='scope3_only') ───────────

CATEGORY_CLASSIFY_PROMPT_SCOPE3 = """You are a Carbon Scope 3 emissions classifier — GHG Protocol categories 1–15.
Analyze the following input and determine which Scope 3 categories from the list below it relates to.
One input can match multiple categories.

Available Scope 3 categories (this is the ONLY list you may classify into):
{categories_json}

Input to analyze:
{input_content}

CRITICAL CONSTRAINT — read carefully:
- You MUST choose only from the categories listed above.
- If the input is about Social topics (employee benefits, training, diversity,
  human rights, community engagement, customer privacy, marketing, product safety),
  Governance topics (board composition, anti-corruption, audit, ethics, tax,
  shareholder rights, related party transactions), or Scope 1 / Scope 2
  emissions (direct combustion, owned vehicles, purchased electricity for
  operations) — return EMPTY matches with reasoning, not a forced fit.
- Do NOT invent categories that are not in the list.
- A single document may relate to multiple Scope 3 categories — be thorough
  WITHIN the list, but conservative OUTSIDE it.

Respond in JSON format ONLY:
{{
    "matches": [
        {{
            "category_id": <int>,
            "category_name": "<name>",
            "confidence": <0.0-1.0>,
            "reasoning": "<brief explanation>"
        }}
    ],
    "no_match_reason": "<set this when matches is empty — e.g. 'Input is a salary slip (Social, not Scope 3)'>"
}}

Rules:
- Include ALL Scope 3 categories that the input could relate to
- Minimum confidence threshold: 0.3
- If the input is NOT a Scope 3 source, return empty matches and explain in no_match_reason
"""

SUBCATEGORY_CLASSIFY_PROMPT_SCOPE3 = """You are a Carbon Scope 3 data classifier performing subcategory matching.
Given the input and the matched Scope 3 category, identify which subcategories the input relates to.

Scope 3 Category: {category_name}
Available subcategories (this is the ONLY list you may classify into):
{subcategories_json}

Input to analyze:
{input_content}

Respond in JSON format ONLY:
{{
    "matches": [
        {{
            "subcategory_id": <int>,
            "subcategory_name": "<name>",
            "confidence": <0.0-1.0>,
            "reasoning": "<brief explanation>"
        }}
    ]
}}

Rules:
- Include ALL subcategories that the input could satisfy
- Minimum confidence threshold: 0.3
- You MUST choose only from the listed subcategories — do not invent new ones
- If the input doesn't fit any subcategory, return empty matches
"""

DATAPOINT_EXTRACT_PROMPT_SCOPE3 = DATAPOINT_EXTRACT_PROMPT
