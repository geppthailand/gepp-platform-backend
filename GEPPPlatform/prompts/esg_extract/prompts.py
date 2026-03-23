"""
ESG Cascade Extraction Prompt Templates
Used by EsgExtractionService for the 3-step cascade:
  1. Category classification
  2. Subcategory classification
  3. Datapoint extraction
"""

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
