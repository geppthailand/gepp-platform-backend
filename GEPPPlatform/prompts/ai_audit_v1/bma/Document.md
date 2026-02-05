# BMA AI Audit V1 - Developer Documentation

## Overview

This document describes the abbreviated output format and audit logic for the Bangkok Metropolitan Administration (BMA) waste audit system using Gemini 2.5 Flash Lite.

---

## System Architecture

### Audit Flow

```
1. Step 1: Material Completeness Check
   ├─ Check: general (required), organic (required), recyclable (required)
   ├─ Check: hazardous (optional)
   └─ If incomplete → reject with code "ncm"

2. Step 2: Per-Material Image Audit (parallel processing)
   ├─ For each material with image:
   │   ├─ 2.1: Correct material + good conditions → approve (code "cc")
   │   ├─ 2.2: Wrong material type → reject (code "wc")
   │   ├─ 2.3: Unclear/blurry image → reject (code "ui")
   │   ├─ 2.4: Heavy contamination (>50%) → reject (code "hc")
   │   └─ 2.5: Light contamination (<50%) → approve with warning (code "lc")
   └─ Return abbreviated JSON output
```

---

## Material Type IDs

| Material | ID  | Key String   |
|----------|-----|--------------|
| General  | 94  | `general`    |
| Organic  | 77  | `organic`    |
| Recyclable | 298 | `recyclable` |
| Hazardous | 113 | `hazardous`  |

---

## Output Format - Field Abbreviations

### Top-Level Fields

| Full Name | Abbreviation | Type | Description | Values |
|-----------|--------------|------|-------------|--------|
| `claimed_type` | `ct` | int | Material type ID claimed by user | 94, 77, 298, 113 |
| `audit_status` | `as` | string | Overall audit result | `"a"` (approve), `"r"` (reject) |
| `confidence_score` | `cs` | float | AI confidence (2 decimal places) | 0.00 to 1.00 |
| `remark` | `rm` | object | Detailed audit information | See below |

### Remark Object (`rm`) Fields

| Full Name | Abbreviation | Type | Description | Values |
|-----------|--------------|------|-------------|--------|
| `code` | `co` | string | Result code | See "Remark Codes" section |
| `severity` | `sv` | string | Issue severity level | `"i"` (info), `"m"` (minor), `"c"` (critical) |
| `details` | `de` | object | Additional information | See below |

### Details Object (`de`) Fields

| Full Name | Abbreviation | Type | Description |
|-----------|--------------|------|-------------|
| `detected` | `dt` | string | Detected material type ID (as string) |
| `wrong_items` | `wi` | array[string] | List of items that caused the audit issue (Thai names, not abbreviated) |

**Important Notes:**
- `wi` (wrong_items) contains ONLY items directly related to the problem indicated by the `co` (code)
- Empty array `[]` if no issues (code "cc") or no problematic items
- If multiple issues exist, report the MOST SEVERE issue only, with `wi` containing only items for that issue
- `reason` field has been **removed** (not used)
- `correction_action` field has been **removed** (not used)
- Former `it` (items) field renamed to `wi` (wrong_items) for clarity

---

## Remark Codes (`co`)

| Code | Full Name | Description | Severity | Audit Status |
|------|-----------|-------------|----------|--------------|
| `ncm` | `non_complete_material` | Missing required materials (general, organic, or recyclable) | `c` | `r` (reject) |
| `cc` | `correct_category` | Material matches claimed type, good condition | `i` | `a` (approve) |
| `wc` | `wrong_category` | Material does not match claimed type | `c` | `r` (reject) |
| `ui` | `unclear_image` | Image is blurry, unclear, too small, or materials in opaque container | `c` | `r` (reject) |
| `hc` | `heavy_contamination` | Contamination >50% (recyclable/hazardous only) | `c` | `r` (reject) |
| `lc` | `light_contamination` | Contamination <50% (recyclable/hazardous only) | `m` | `a` (approve with warning) |

---

## Severity Levels (`sv`)

| Code | Full Name | Description | Typical Action |
|------|-----------|-------------|----------------|
| `i` | `info` | Informational - everything correct | Approve |
| `m` | `minor` | Minor issue - warning but can pass | Approve with warning |
| `c` | `critical` | Critical issue - must reject | Reject |

---

## Audit Status (`as`)

| Code | Full Name | Description |
|------|-----------|-------------|
| `a` | `approve` | Transaction passed audit |
| `r` | `reject` | Transaction failed audit |

---

## Audit Rules

### Step 1: Material Completeness Check

**Required materials:** `general` (94), `organic` (77), `recyclable` (298)
**Optional materials:** `hazardous` (113)

**Rule:** If any of the 3 required materials are missing:
- `as`: `"r"`
- `rm.co`: `"ncm"`
- `rm.sv`: `"c"`

---

### Step 2: Per-Material Image Audit

**CRITICAL - Severity Prioritization:**
- If multiple issues are detected, report ONLY the MOST SEVERE issue
- Severity order: **critical (c) > minor (m) > info (i)**
- The `co` code must represent the most critical issue found
- The `wi` array must contain ONLY items related to that specific code
- Example: If both wrong_category (critical) AND light_contamination (minor) exist, report only wrong_category

For each material that has an image attached, apply the following rules:

#### 2.1 Correct Category (`cc`)
- **Condition:** Material matches claimed type AND good image quality AND good material condition (no issues)
- **Output:**
  - `as`: `"a"`
  - `rm.co`: `"cc"`
  - `rm.sv`: `"i"`
  - `rm.de.dt`: Material ID as string
  - `rm.de.wi`: Empty array `[]`

#### 2.2 Wrong Category (`wc`)
- **Condition:** Detected material type does NOT match claimed type
- **Priority:** CRITICAL - Takes precedence over contamination or other minor issues
- **Output:**
  - `as`: `"r"`
  - `rm.co`: `"wc"`
  - `rm.sv`: `"c"`
  - `rm.de.dt`: Detected material ID as string
  - `rm.de.wi`: Array of ONLY wrong category items (Thai names)

#### 2.3 Unclear Image (`ui`)
- **Condition:** Any of:
  - Image is blurry or out of focus
  - Image is too small or too dark
  - Materials are inside opaque bags/containers (cannot see inside)
  - Cannot identify materials clearly
- **Priority:** CRITICAL - Equal to wrong_category
- **Output:**
  - `as`: `"r"`
  - `rm.co`: `"ui"`
  - `rm.sv`: `"c"`
  - `rm.de.dt`: `"0"` (unknown)
  - `rm.de.wi`: Description array of image quality issues (e.g., `["ภาพเบลอ", "มองไม่เห็นวัสดุ"]`)

#### 2.4 Heavy Contamination (`hc`)
- **Applies to:** `recyclable` (298) and `hazardous` (113) only
- **Condition:** Material contamination >50% of total volume
  - Food stains, grease, dirt
  - Biological waste contamination
- **Priority:** CRITICAL - But lower than wrong_category or unclear_image
- **Output:**
  - `as`: `"r"`
  - `rm.co`: `"hc"`
  - `rm.sv`: `"c"`
  - `rm.de.dt`: Material ID as string
  - `rm.de.wi`: Array of ONLY heavily contaminated items

#### 2.5 Light Contamination (`lc`)
- **Applies to:** `recyclable` (298) and `hazardous` (113) only
- **Condition:** Material contamination <50% of total volume
- **Priority:** MINOR - Lowest priority, only report if no critical issues
- **Output:**
  - `as`: `"a"` (approve with warning)
  - `rm.co`: `"lc"`
  - `rm.sv`: `"m"`
  - `rm.de.dt`: Material ID as string
  - `rm.de.wi`: Array of ONLY lightly contaminated items

---

## Example Outputs

### Example 1: Correct General Waste (No Issues)

```json
{
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
}
```

### Example 2: Wrong Category (Organic items in General waste)

**Note:** Only wrong category items are listed in `wi`

```json
{
  "ct": 94,
  "as": "r",
  "cs": 0.88,
  "rm": {
    "co": "wc",
    "sv": "c",
    "de": {
      "dt": "77",
      "wi": ["เศษผัก", "เปลือกผลไม้", "เศษอาหาร"]
    }
  }
}
```

### Example 3: Unclear Image

**Note:** `wi` contains image quality issues, not material items

```json
{
  "ct": 298,
  "as": "r",
  "cs": 0.32,
  "rm": {
    "co": "ui",
    "sv": "c",
    "de": {
      "dt": "0",
      "wi": ["ภาพเบลอมาก", "มองไม่เห็นรายละเอียดวัสดุ"]
    }
  }
}
```

### Example 4: Heavy Contamination (Recyclable)

**Note:** Only heavily contaminated items are listed

```json
{
  "ct": 298,
  "as": "r",
  "cs": 0.91,
  "rm": {
    "co": "hc",
    "sv": "c",
    "de": {
      "dt": "298",
      "wi": ["ขวดพลาสติกเปื้อนน้ำมันหนัก", "กล่องกระดาษเปื้อนอาหารเยอะ"]
    }
  }
}
```

### Example 5: Light Contamination (Recyclable) - Pass with Warning

**Note:** Only lightly contaminated items listed

```json
{
  "ct": 298,
  "as": "a",
  "cs": 0.87,
  "rm": {
    "co": "lc",
    "sv": "m",
    "de": {
      "dt": "298",
      "wi": ["ขวดน้ำเปื้อนเล็กน้อย"]
    }
  }
}
```

### Example 6: Non-Complete Materials (Step 1 Failure)

```json
{
  "ct": 0,
  "as": "r",
  "cs": 0.00,
  "rm": {
    "co": "ncm",
    "sv": "c",
    "de": {
      "dt": "0",
      "wi": ["ไม่มีขยะอินทรีย์", "ไม่มีขยะรีไซเคิล"]
    }
  }
}
```

### Example 7: Multiple Issues - Severity Prioritization

**Scenario:** Recyclable waste contains both wrong category items AND light contamination

**Correct Output:** Report ONLY the most severe issue (wrong_category)

```json
{
  "ct": 298,
  "as": "r",
  "cs": 0.82,
  "rm": {
    "co": "wc",
    "sv": "c",
    "de": {
      "dt": "94",
      "wi": ["ถุงพลาสติกสกปรก", "ผ้าเช็ดปาก", "ไม้จิ้มฟัน"]
    }
  }
}
```

---

## AI Model Configuration

- **Model:** `gemini-2.5-flash-lite`
- **Temperature:** `0.0` (deterministic)
- **Max Output Tokens:** `2048`
- **Thinking Budget:** `0` (no extended reasoning)

---

## Implementation Notes

### Using LangChain with Gemini

The system uses `langchain-google-genai` for structured prompting:

```python
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import PromptTemplate

# Initialize model
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash-lite",
    temperature=0.0,
    max_output_tokens=2048
)

# Load prompt template from YAML
template = load_material_prompt(material_key)
prompt = PromptTemplate(
    template=template,
    input_variables=["claimed_type", "image_url", "output_format"]
)

# Generate response
chain = prompt | llm
response = chain.invoke({
    "claimed_type": material_key,
    "image_url": image_url,
    "output_format": output_format_text
})
```

### Parallel Processing

Material audits are processed in parallel using `ThreadPoolExecutor` with max 4 concurrent workers for optimal performance.

### Token Usage Tracking

The system tracks token usage for each Gemini API call:
- `input_tokens`: Prompt + image tokens
- `output_tokens`: Generated response tokens
- `total_tokens`: Sum of input and output

---

## Error Handling

### Parse Error Response

If the AI returns invalid JSON:

```json
{
  "ct": 0,
  "as": "r",
  "cs": 0.00,
  "rm": {
    "co": "pe",
    "sv": "c",
    "de": {
      "dt": "0",
      "it": ["ไม่สามารถแปลงผลลัพธ์จาก AI ได้"]
    }
  }
}
```

### Image Download Error

If image cannot be downloaded:

```json
{
  "ct": 0,
  "as": "r",
  "cs": 0.00,
  "rm": {
    "co": "ie",
    "sv": "c",
    "de": {
      "dt": "0",
      "it": ["ไม่สามารถดาวน์โหลดภาพได้"]
    }
  }
}
```

---

## Complete Abbreviation Reference Table

| Category | Full Name | Abbreviation |
|----------|-----------|--------------|
| **Top Level** |
| | claimed_type | ct |
| | audit_status | as |
| | confidence_score | cs |
| | remark | rm |
| **Remark** |
| | code | co |
| | severity | sv |
| | details | de |
| **Details** |
| | detected | dt |
| | wrong_items | wi |
| **Audit Status Values** |
| | approve | a |
| | reject | r |
| **Severity Values** |
| | info | i |
| | minor | m |
| | critical | c |
| **Remark Codes** |
| | non_complete_material | ncm |
| | correct_category | cc |
| | wrong_category | wc |
| | unclear_image | ui |
| | heavy_contamination | hc |
| | light_contamination | lc |
| | parse_error | pe |
| | image_error | ie |

---

## Contamination Assessment Guidelines

### For Recyclable Materials (298)

**Heavy Contamination (>50%):** REJECT
- Bottles with remaining liquid >50%
- Containers with food residue covering >50%
- Paper/cardboard soaked with grease/oil
- Metal cans with significant rust or corrosion

**Light Contamination (<50%):** APPROVE WITH WARNING
- Bottles with small amount of residue
- Containers with minor stains
- Slightly dirty recyclables that can be cleaned

### For Hazardous Materials (113)

**Heavy Contamination (>50%):** REJECT
- Batteries leaking chemical fluids
- Electronics with visible corrosion
- Chemical containers with spills

**Light Contamination (<50%):** APPROVE WITH WARNING
- Batteries with minor surface dirt
- Electronics with dust buildup
- Clean chemical containers

---

## API Response Structure

### Success Response

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
                "it": []
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

---

## Version History

- **v1.0** (2026-01-28): Initial abbreviated format with 5 audit rules
  - Step 1: Material completeness check
  - Step 2: Per-material image audit with contamination detection
  - Gemini 2.5 Flash Lite integration with LangChain
  - Token usage tracking
  - Parallel processing support

---

## Contact & Support

For questions or issues, contact the GEPP Platform development team.

**Last Updated:** 2026-01-28
