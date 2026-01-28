# BMA AI Audit System - Implementation Summary

## Overview

This directory contains the complete implementation of the Bangkok Metropolitan Administration (BMA) waste audit system using Gemini 2.0 Flash Exp with LangChain.

## Files Structure

```
bma/
├── Document.md           # Complete developer documentation with abbreviations
├── README.md            # This file
├── output_format.yaml   # Abbreviated output format template
├── general.yaml         # Prompt template for general waste
├── organic.yaml         # Prompt template for organic waste
├── recyclable.yaml      # Prompt template for recyclable waste (with contamination rules)
└── hazardous.yaml       # Prompt template for hazardous waste (with contamination rules)
```

## Key Features

### 1. Two-Step Audit Process

**Step 1: Material Completeness Check**
- Verifies presence of required materials: `general`, `organic`, `recyclable`
- `hazardous` is optional
- Returns `ncm` (non_complete_material) code if any required material is missing

**Step 2: Per-Material Image Audit**
- Processes each material type independently in parallel
- Uses material-specific prompts
- Applies contamination rules for recyclable and hazardous only
- Returns abbreviated JSON for space optimization

### 2. Five Audit Rules

| # | Rule | Code | Description | Applies To |
|---|------|------|-------------|-----------|
| 1 | Not Complete | `ncm` | Missing required materials | All (Step 1) |
| 2.1 | Correct Category | `cc` | Material matches, good condition | All |
| 2.2 | Wrong Category | `wc` | Material doesn't match claimed type | All |
| 2.4 | Unclear Image | `ui` | Blurry/opaque/cannot see materials | All |
| 2.5 | Heavy Contamination | `hc` | >50% contamination | Recyclable, Hazardous |
| 2.6 | Light Contamination | `lc` | <50% contamination (warning) | Recyclable, Hazardous |

### 3. Abbreviated Output Format

Space-optimized JSON structure:

```json
{
  "ct": 94,           // claimed_type (material ID)
  "as": "a",          // audit_status (a=approve, r=reject)
  "cs": 0.95,         // confidence_score (2 decimals)
  "rm": {             // remark
    "co": "cc",       // code
    "sv": "i",        // severity (i=info, m=minor, c=critical)
    "de": {           // details
      "dt": "94",     // detected material type (as string)
      "wi": []        // wrong_items - ONLY items that caused the issue (Thai names)
    }
  }
}
```

**Important - `wi` (wrong_items) Logic:**
- Contains ONLY items directly related to the problem indicated by `co` (code)
- Empty array `[]` if no issues (code "cc")
- If multiple issues exist, report the MOST SEVERE issue only
- Severity order: critical (c) > minor (m) > info (i)
- Example: Wrong category (critical) takes priority over contamination (minor)

## Material Type IDs

| Material | ID | Key |
|----------|-----|-----|
| General | 94 | `general` |
| Organic | 77 | `organic` |
| Recyclable | 298 | `recyclable` |
| Hazardous | 113 | `hazardous` |

## Technology Stack

- **AI Model:** Gemini 2.0 Flash Exp
- **Framework:** LangChain (`langchain-google-genai`)
- **Parallel Processing:** ThreadPoolExecutor (max 4 workers)
- **Image Processing:** PIL, base64 encoding
- **Configuration:** YAML templates

## Usage

### From Backend Code

```python
from GEPPPlatform.services.custom.functions.ai_audit_v1 import bma_audit_rule_set

result = bma_audit_rule_set.execute(
    db_session=session,
    organization_id=8,
    transaction_ids=[123, 456],
    body={}
)
```

### API Endpoint

```bash
POST https://api.geppdata.com/v1/api/userapi/{api_key}/ai_audit/v1/call
Authorization: Bearer {jwt_token}

# Body structure defined in main.py
```

## Response Structure

```json
{
  "success": true,
  "rule_set": "bma_audit_rule_set",
  "organization_id": 8,
  "total_transactions": 1,
  "summary": {
    "step_1_passed": 1,
    "step_1_failed": 0,
    "step_2_materials_audited": 4
  },
  "token_usage": {
    "input_tokens": 15234,
    "output_tokens": 512,
    "total_tokens": 15746
  },
  "results": [
    {
      "transaction_id": 123,
      "ext_id_1": "2026-Q1",
      "ext_id_2": "0000000000001",
      "step_1": {
        "status": "pass",
        "required": ["general", "organic", "recyclable"],
        "present": ["general", "organic", "recyclable", "hazardous"],
        "missing": []
      },
      "step_2": [
        {
          "material": "general",
          "record_id": 456,
          "success": true,
          "result": {
            "ct": 94,
            "as": "a",
            "cs": 0.95,
            "rm": {
              "co": "cc",
              "sv": "i",
              "de": {
                "dt": "94",
                "wi": []
              }
            }
          },
          "usage": {
            "input_tokens": 3245,
            "output_tokens": 128,
            "total_tokens": 3373
          }
        }
      ]
    }
  ]
}
```

## Environment Variables

```bash
GEMINI_API_KEY=your_api_key_here
```

## Dependencies

Install required packages:

```bash
pip install langchain-google-genai langchain-core pillow pyyaml
```

## Contamination Assessment

### For Recyclable (298) and Hazardous (113) Only

**Heavy Contamination (>50%) → REJECT**
- Bottles >50% full of liquid
- Containers with >50% food residue
- Paper soaked with grease/oil
- Batteries with leakage on >50% items

**Light Contamination (<50%) → APPROVE with WARNING**
- Bottles with <50% residue
- Containers with <50% stains
- Minor dirt/dust buildup

**General (94) and Organic (77)**
- NO contamination assessment
- Contamination is expected and normal

## Error Codes

| Code | Meaning | Severity |
|------|---------|----------|
| `ncm` | non_complete_material | critical |
| `cc` | correct_category | info |
| `wc` | wrong_category | critical |
| `ui` | unclear_image | critical |
| `hc` | heavy_contamination | critical |
| `lc` | light_contamination | minor |
| `pe` | parse_error | critical |
| `ie` | image_error | critical |

## Testing

Test with sample data from `backend/test_bma_transactions_v1.csv`:
- 100 transactions
- 25 correct (case 1)
- 25 incomplete (case 2)
- 25 shuffled wrong types (case 3)
- 25 unknown/unclear (case 4)

## Documentation

For complete documentation including all abbreviations, rules, and examples, see:
- **[Document.md](./Document.md)** - Full developer documentation

## Version

- **Version:** 1.0
- **Last Updated:** 2026-01-28
- **Model:** gemini-2.0-flash-exp
- **Framework:** LangChain

## Contact

GEPP Platform Development Team
