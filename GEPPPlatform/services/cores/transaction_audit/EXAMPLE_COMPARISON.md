# Transaction Audit API Call Comparison

## Before Optimization

### API Request Structure
```python
messages = [
    {
        "role": "system",
        "content": "You are a professional waste management auditor with expertise in compliance and quality control. You can analyze documents, receipts, and waste material images to verify transaction details."
    },
    {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": """
You are an expert AI auditor for waste management transactions. Evaluate the following transaction against EACH provided audit rule individually.

TRANSACTION DATA:
{
    "transaction_id": 123,
    "organization_id": 1,
    "user_id": 45,
    "transaction_method": "buy",
    "status": "pending",
    "weight_kg": 150.5,
    "total_amount": 3500.00,
    "transaction_date": "2024-01-15T10:00:00Z",
    "arrival_date": "2024-01-15T14:00:00Z",
    "hazardous_level": "non_hazardous",
    "treatment_method": "recycling",
    "notes": "Bulk plastic collection",
    "images": ["transaction_img_1.jpg"],
    "records": [
        {
            "record_id": 100,
            "material_type": "PET Plastic",
            "material_name_th": "พลาสติก PET",
            "material_code": "PET-001",
            "quantity": 100,
            "weight_kg": 50.0,
            "unit": "kg",
            "unit_price": 15.0,
            "total_value": 1500.0,
            "material_condition": "good",
            "quality_score": 8.5,
            "contamination_level": "low",
            "processing_notes": "Clean PET bottles",
            "images": ["record_100_img_1.jpg", "record_100_img_2.jpg"],
            "status": "active",
            "hazardous_level": "non_hazardous"
        },
        {
            "record_id": 101,
            "material_type": "HDPE Plastic",
            "material_name_th": "พลาสติก HDPE",
            "material_code": "HDPE-002",
            "quantity": 100,
            "weight_kg": 100.5,
            "unit": "kg",
            "unit_price": 20.0,
            "total_value": 2000.0,
            "material_condition": "fair",
            "quality_score": 7.0,
            "contamination_level": "medium",
            "processing_notes": "Mixed HDPE containers",
            "images": ["record_101_img_1.jpg"],
            "status": "active",
            "hazardous_level": "non_hazardous"
        }
    ]
}

AUDIT RULES TO EVALUATE:

Rule ID: DC-01
DB ID: 1
Name: Weight Discrepancy Check
Type: consistency
Condition: Verify total weight equals sum of record weights (±5% tolerance)
Thresholds: 5% variance
Metrics: Total weight, record weights
Actions: [{"type": "system_action", "action": "reject", "message": "Weight mismatch detected"}]

Rule ID: DC-02
DB ID: 2
Name: Material Type Verification
Type: accuracy
Condition: Verify material type matches visual evidence in images
Thresholds: N/A
Metrics: Material type, visual characteristics
Actions: [{"type": "system_action", "action": "reject", "message": "Material type mismatch"}]

Rule ID: DC-03
DB ID: 3
Name: Date Consistency Check
Type: consistency
Condition: Transaction date should not be before invoice/receipt date
Thresholds: N/A
Metrics: Transaction date, document dates
Actions: [{"type": "system_action", "action": "reject", "message": "Date inconsistency"}]

Rule ID: DC-04
DB ID: 4
Name: Price Range Validation
Type: validation
Condition: Unit prices should be within market range (±30%)
Thresholds: 30% variance
Metrics: Unit prices, market rates
Actions: [{"type": "system_action", "action": "warn", "message": "Price outside normal range"}]

Rule ID: DC-05
DB ID: 5
Name: Documentation Completeness
Type: completeness
Condition: Required documents (invoice, weight slip) must be present
Thresholds: N/A
Metrics: Document presence
Actions: [{"type": "system_action", "action": "reject", "message": "Missing required documents"}]

CRITICAL INSTRUCTIONS:
1. Evaluate the transaction against EVERY audit rule provided
2. For each rule, determine if it is triggered (true/false) based on the rule conditions and transaction data
3. If a rule is triggered, provide a brief, specific message explaining why
4. If a rule is not triggered, set trigger to false and provide a brief confirmation message

YOU MUST respond with a valid JSON object in this EXACT format:
{
    "transaction_id": 123,
    "audits": [
        {
            "rule_id": "<rule_id from rule>",
            "id": <database_id_of_rule>,
            "trigger": true or false,
            "message": "<the specific message that explains why the rule was triggered (not general, specific with the situation)>",
            "reasons": ["<reason1>", ...]
        }
    ]
}

IMPORTANT REQUIREMENTS:
- Include ALL rules in the audits array, even if not triggered
- Keep messages brief (max 50 words)
- Use exact rule_id and id values from the provided rules
- Respond with ONLY valid JSON, no additional text
- Focus on factual evaluation based on rule conditions and transaction data

ADDITIONAL IMAGE ANALYSIS INSTRUCTIONS:
You have been provided with 4 presigned image URLs related to this transaction. These images may include:
- Waste material photos showing actual materials, quantities, and conditions
- Receipts, invoices, or transaction documents
- Weight scale readings or measurement documentation
- Quality certification documents
- Processing or transport documentation

When analyzing these images:
1. **OCR Analysis**: Extract any text, numbers, weights, quantities, dates, or prices from the images
2. **Visual Verification**: Compare visual evidence with the reported transaction data
3. **Discrepancy Detection**: Look for inconsistencies between images and reported data
4. **Document Verification**: Verify authenticity and completeness of any documents shown
5. **Material Assessment**: Evaluate actual material condition, contamination level, and type consistency

Pay special attention to:
- Weight/quantity discrepancies between images and reported data
- Material type mismatches (e.g., reported plastic but image shows metal)
- Date inconsistencies between documents and transaction dates
- Quality condition differences (reported "good" but image shows contaminated material)
- Price variations between receipts/invoices and reported amounts
- Missing required documentation or certifications

For each audit rule evaluation, consider both the transaction data AND the visual evidence from images.
If images contradict the reported data, prioritize the visual evidence and flag appropriate violations.

RECORDS DATA FOR IMAGE CROSS-REFERENCE:

Record #1 (ID: 100):
- Material: PET Plastic (พลาสติก PET)
- Quantity: 100 kg
- Weight: 50.0 kg
- Unit Price: 15.0 per kg
- Total Value: 1500.0
- Condition: good
- Quality Score: 8.5
- Contamination Level: low
- Images Count: 2

Record #2 (ID: 101):
- Material: HDPE Plastic (พลาสติก HDPE)
- Quantity: 100 kg
- Weight: 100.5 kg
- Unit Price: 20.0 per kg
- Total Value: 2000.0
- Condition: fair
- Quality Score: 7.0
- Contamination Level: medium
- Images Count: 1

Respond only with valid JSON format as specified above.
"""
            },
            {"type": "image_url", "image_url": {"url": "https://presigned-url-1", "detail": "high"}},
            {"type": "image_url", "image_url": {"url": "https://presigned-url-2", "detail": "high"}},
            {"type": "image_url", "image_url": {"url": "https://presigned-url-3", "detail": "high"}},
            {"type": "image_url", "image_url": {"url": "https://presigned-url-4", "detail": "high"}}
        ]
    }
]
```

**Estimated Tokens:** ~2,200 input tokens

### API Response (All Rules)
```json
{
    "transaction_id": 123,
    "audits": [
        {
            "rule_id": "DC-01",
            "id": 1,
            "trigger": false,
            "message": "Total weight 150.5kg matches sum of records (50.0 + 100.5 = 150.5kg). No discrepancy found.",
            "reasons": []
        },
        {
            "rule_id": "DC-02",
            "id": 2,
            "trigger": false,
            "message": "Material types verified: PET and HDPE plastics match visual evidence in images. Containers show correct plastic types.",
            "reasons": []
        },
        {
            "rule_id": "DC-03",
            "id": 3,
            "trigger": true,
            "message": "Date inconsistency detected: Invoice in image shows date 2024-01-12, but transaction date is 2024-01-15.",
            "reasons": [
                "Invoice date from OCR: 2024-01-12",
                "Reported transaction date: 2024-01-15",
                "Transaction date should not precede invoice date"
            ]
        },
        {
            "rule_id": "DC-04",
            "id": 4,
            "trigger": false,
            "message": "Unit prices within acceptable range: PET at 15.0/kg and HDPE at 20.0/kg are within market norms.",
            "reasons": []
        },
        {
            "rule_id": "DC-05",
            "id": 5,
            "trigger": true,
            "message": "Missing required documentation: Weight slip not found in provided images. Only invoice visible.",
            "reasons": [
                "Invoice present and verified",
                "Weight slip missing",
                "Documentation incomplete"
            ]
        }
    ]
}
```

**Estimated Tokens:** ~350 output tokens

**Total:** ~2,550 tokens per transaction

---

## After Optimization

### API Request Structure
```python
messages = [
    {
        "role": "system",
        "content": "You are a waste management auditor. Analyze transactions and flag only violations. Be concise."
    },
    {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": """
Audit waste transaction against rules. Evaluate each rule and return triggered violations only.

RULES (ref by id):
[{"id":1,"rule_id":"DC-01","name":"Weight Discrepancy Check","type":"consistency","condition":"Verify total weight equals sum of record weights (±5% tolerance)","thresholds":"5% variance","metrics":"Total weight, record weights"},{"id":2,"rule_id":"DC-02","name":"Material Type Verification","type":"accuracy","condition":"Verify material type matches visual evidence in images","thresholds":"N/A","metrics":"Material type, visual characteristics"},{"id":3,"rule_id":"DC-03","name":"Date Consistency Check","type":"consistency","condition":"Transaction date should not be before invoice/receipt date","thresholds":"N/A","metrics":"Transaction date, document dates"},{"id":4,"rule_id":"DC-04","name":"Price Range Validation","type":"validation","condition":"Unit prices should be within market range (±30%)","thresholds":"30% variance","metrics":"Unit prices, market rates"},{"id":5,"rule_id":"DC-05","name":"Documentation Completeness","type":"completeness","condition":"Required documents (invoice, weight slip) must be present","thresholds":"N/A","metrics":"Document presence"}]

TRANSACTION:
{"transaction_id":123,"organization_id":1,"user_id":45,"transaction_method":"buy","status":"pending","weight_kg":150.5,"total_amount":3500.0,"transaction_date":"2024-01-15T10:00:00Z","arrival_date":"2024-01-15T14:00:00Z","hazardous_level":"non_hazardous","treatment_method":"recycling","notes":"Bulk plastic collection","images":["transaction_img_1.jpg"],"records":[{"record_id":100,"material_type":"PET Plastic","material_name_th":"พลาสติก PET","material_code":"PET-001","quantity":100,"weight_kg":50.0,"unit":"kg","unit_price":15.0,"total_value":1500.0,"material_condition":"good","quality_score":8.5,"contamination_level":"low","processing_notes":"Clean PET bottles","images":["record_100_img_1.jpg","record_100_img_2.jpg"],"status":"active","hazardous_level":"non_hazardous"},{"record_id":101,"material_type":"HDPE Plastic","material_name_th":"พลาสติก HDPE","material_code":"HDPE-002","quantity":100,"weight_kg":100.5,"unit":"kg","unit_price":20.0,"total_value":2000.0,"material_condition":"fair","quality_score":7.0,"contamination_level":"medium","processing_notes":"Mixed HDPE containers","images":["record_101_img_1.jpg"],"status":"active","hazardous_level":"non_hazardous"}]}

CRITICAL: Images for each transaction_record apply ONLY to that specific record. Do NOT process images across different records unless explicitly instructed by rules.

Respond ONLY rejected items in this JSON format:
{
    "tr_id": 123,
    "violations": [
        {
            "id": <rule_db_id>,
            "msg": "<short specific rejection reason (max 30 words)>"
        }
    ]
}

If NO violations: {"tr_id": 123, "violations": []}
Only include triggered rules. Keep messages concise.

IMAGE ANALYSIS:
- Extract text/numbers from documents (OCR)
- Verify weights, quantities, dates, prices match reported data
- Check material type consistency with images
- Identify discrepancies or missing docs
- CRITICAL: Each record's images apply ONLY to that record

If images contradict data, flag violation with specific reason.
"""
            },
            {"type": "text", "text": "TRANSACTION-LEVEL IMAGES:"},
            {"type": "image_url", "image_url": {"url": "https://presigned-url-1", "detail": "high"}},
            {"type": "text", "text": "RECORD #1 (ID:100) - PET Plastic - 50.0kg:"},
            {"type": "image_url", "image_url": {"url": "https://presigned-url-2", "detail": "high"}},
            {"type": "image_url", "image_url": {"url": "https://presigned-url-3", "detail": "high"}},
            {"type": "text", "text": "RECORD #2 (ID:101) - HDPE Plastic - 100.5kg:"},
            {"type": "image_url", "image_url": {"url": "https://presigned-url-4", "detail": "high"}}
        ]
    }
]
```

**Estimated Tokens:** ~750 input tokens (66% reduction)

### API Response (Violations Only)
```json
{
    "tr_id": 123,
    "violations": [
        {
            "id": 3,
            "msg": "Invoice date 2024-01-12 precedes transaction date 2024-01-15"
        },
        {
            "id": 5,
            "msg": "Weight slip missing from documents"
        }
    ]
}
```

**Estimated Tokens:** ~45 output tokens (87% reduction)

**Total:** ~795 tokens per transaction (69% reduction)

---

## Token Savings Breakdown

| Metric | Before | After | Reduction |
|--------|--------|-------|-----------|
| Input Tokens | 2,200 | 750 | 66% |
| Output Tokens | 350 | 45 | 87% |
| Total Tokens | 2,550 | 795 | 69% |

## Cost Impact (Example: 100 Transactions)

Assuming GPT-4 Vision pricing: $0.01/1K input tokens, $0.03/1K output tokens

### Before
- Input: 220,000 tokens × $0.01/1K = $2.20
- Output: 35,000 tokens × $0.03/1K = $1.05
- **Total: $3.25**

### After
- Input: 75,000 tokens × $0.01/1K = $0.75
- Output: 4,500 tokens × $0.03/1K = $0.14
- **Total: $0.89**

**Savings: $2.36 (73% cost reduction)**

## Key Optimizations Applied

1. ✅ ID-based rule references (database ID instead of full details)
2. ✅ Violations-only output (no need to list all rules)
3. ✅ Compact JSON formatting (no pretty printing)
4. ✅ Concise system message
5. ✅ Structured record-image grouping with clear labels
6. ✅ Minimal instructions focused on critical points
7. ✅ 30-word message limit enforcement
8. ✅ Removed verbose explanations and examples
