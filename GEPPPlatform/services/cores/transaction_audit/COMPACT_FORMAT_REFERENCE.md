# Ultra-Compact Audit Format Reference Guide

## Overview
The audit results are stored in an ultra-compact JSON format to minimize storage size and reduce token usage.

## Transaction-Level Format (`transaction.ai_audit_note`)

### Structure
```json
{
    "s": "rejected",
    "v": [
        {"id": 42, "m": "ภาพไม่ใช่ภาพจริงของขยะ หรือไม่เห็นประเภทขยะชัดเจน"}
    ],
    "t": {
        "input_tokens": 3504,
        "output_tokens": 1471,
        "total_tokens": 4975
    },
    "at": "2024-01-15T10:30:00.123456+00:00"
}
```

### Field Reference

| Short Key | Full Name | Type | Description |
|-----------|-----------|------|-------------|
| `s` | status | string | Audit status: `"approved"` or `"rejected"` |
| `v` | violations | array | Array of violations (empty if approved) |
| `v[].id` | rule_db_id | integer | Database ID of triggered rule (use to lookup rule details) |
| `v[].m` | message | string | Specific violation message (max 30 words) |
| `t` | token_usage | object | Token usage for this transaction's audit |
| `t.input_tokens` | input_tokens | integer | Input tokens used |
| `t.output_tokens` | output_tokens | integer | Output tokens used |
| `t.total_tokens` | total_tokens | integer | Total tokens used |
| `at` | audited_at | string | ISO timestamp of audit |

### Example: Approved Transaction
```json
{
    "s": "approved",
    "v": [],
    "t": {"input_tokens": 2217, "output_tokens": 1241, "total_tokens": 3458},
    "at": "2024-01-15T10:30:00Z"
}
```

### Example: Rejected Transaction (Multiple Violations)
```json
{
    "s": "rejected",
    "v": [
        {"id": 41, "m": "ชนิดวัสดุในรูปภาพไม่ตรงกับ General Waste ของรายการ"},
        {"id": 42, "m": "รูปภาพไม่ใช่รูปขยะจริง หรือไม่เห็นขยะชัดเจน"}
    ],
    "t": {"input_tokens": 3500, "output_tokens": 1694, "total_tokens": 5194},
    "at": "2024-01-15T10:31:00Z"
}
```

---

## Batch-Level Format (`transaction_audit_history.audit_info`)

### Structure
```json
{
    "transaction_results": {
        "25": {
            "s": "rejected",
            "v": [{"id": 42, "m": "ภาพไม่ใช่ภาพจริงของขยะ"}],
            "t": {"i": 3504, "o": 1471, "tot": 4975}
        },
        "27": {
            "s": "approved",
            "v": [],
            "t": {"i": 2217, "o": 1241, "tot": 3458}
        }
    },
    "summary": {
        "total_transactions": 5,
        "processed_transactions": 5,
        "approved_count": 1,
        "rejected_count": 4,
        "token_usage": {
            "total_input_tokens": 12087,
            "total_output_tokens": 6526,
            "total_tokens": 18613
        }
    }
}
```

### Field Reference

| Short Key | Full Name | Type | Description |
|-----------|-----------|------|-------------|
| `transaction_results` | - | object | Map of transaction_id → audit result |
| `s` | status | string | Audit status: `"approved"` or `"rejected"` |
| `v` | violations | array | Array of violations (empty if approved) |
| `v[].id` | rule_db_id | integer | Database ID of triggered rule |
| `v[].m` | message | string | Violation message |
| `t.i` | input_tokens | integer | Input tokens for this transaction |
| `t.o` | output_tokens | integer | Output tokens for this transaction |
| `t.tot` | total_tokens | integer | Total tokens for this transaction |
| `summary` | - | object | Batch summary statistics |

---

## Usage Examples

### Reading Transaction Audit Note (Python)
```python
import json

# Load audit note from transaction
audit_note = json.loads(transaction.ai_audit_note)

# Check status
if audit_note['s'] == 'rejected':
    print(f"Transaction rejected with {len(audit_note['v'])} violations")

    # Get violations
    for violation in audit_note['v']:
        rule_db_id = violation['id']
        message = violation['m']

        # Lookup rule details from database
        rule = db.query(AuditRule).filter(AuditRule.id == rule_db_id).first()
        print(f"Rule {rule.rule_id} ({rule.rule_name}): {message}")

# Check token usage
tokens = audit_note['t']
print(f"Token usage: {tokens['total_tokens']} (in: {tokens['input_tokens']}, out: {tokens['output_tokens']})")
```

### Reading Batch History (Python)
```python
import json

# Load batch audit info
audit_info = audit_history.audit_info

# Get summary statistics
summary = audit_info['summary']
print(f"Batch processed {summary['processed_transactions']} transactions")
print(f"Approved: {summary['approved_count']}, Rejected: {summary['rejected_count']}")
print(f"Total tokens used: {summary['token_usage']['total_tokens']}")

# Iterate through transaction results
for transaction_id, result in audit_info['transaction_results'].items():
    status = result['s']
    violations_count = len(result['v'])
    tokens = result['t']['tot']

    print(f"Transaction {transaction_id}: {status} ({violations_count} violations, {tokens} tokens)")

    # Get specific violations
    for violation in result['v']:
        print(f"  - Rule ID {violation['id']}: {violation['m']}")
```

### SQL Query to Get Rejected Transactions with Violations
```sql
-- Get all rejected transactions with their violation details
SELECT
    t.id,
    t.ai_audit_note->>'s' as status,
    jsonb_array_length(t.ai_audit_note->'v') as violation_count,
    t.ai_audit_note->'t'->>'total_tokens' as tokens_used,
    t.ai_audit_note->>'at' as audited_at
FROM transactions t
WHERE
    t.ai_audit_note->>'s' = 'rejected'
    AND jsonb_array_length(t.ai_audit_note->'v') > 0;

-- Get violations with rule details
SELECT
    t.id as transaction_id,
    violation->>'id' as rule_db_id,
    violation->>'m' as violation_message,
    ar.rule_id,
    ar.rule_name
FROM
    transactions t,
    jsonb_array_elements(t.ai_audit_note->'v') as violation
LEFT JOIN audit_rules ar ON ar.id = (violation->>'id')::bigint
WHERE
    t.ai_audit_note->>'s' = 'rejected';
```

---

## Migration from Old Format

If you have old format data:

### Old Format
```json
{
    "status": "rejected",
    "summary": "Transaction rejected. 1 violation(s) found.",
    "violations": [
        {"rule_id": "WASTE IMAGE", "rule_db_id": 42, "msg": "ภาพไม่ใช่ภาพจริงของขยะ"}
    ],
    "token_usage": {"input_tokens": 3504, "output_tokens": 1471, "total_tokens": 4975},
    "audited_at": "2024-01-15T10:30:00Z"
}
```

### New Format (30% smaller)
```json
{
    "s": "rejected",
    "v": [
        {"id": 42, "m": "ภาพไม่ใช่ภาพจริงของขยะ"}
    ],
    "t": {"input_tokens": 3504, "output_tokens": 1471, "total_tokens": 4975},
    "at": "2024-01-15T10:30:00Z"
}
```

### Removed Fields
- ❌ `summary` - Can be generated from `s` and `v.length`
- ❌ `rule_id` - Lookup via `rule_db_id` from database
- ❌ `rule_db_id` renamed to just `id`

---

## Benefits

1. **Storage Efficiency:** ~30% reduction in JSON size
2. **Database Performance:** Smaller JSONB columns = faster queries
3. **Cleaner Data:** No redundant information
4. **Fast Lookups:** Use `rule_db_id` to join with `audit_rules` table

## Need Full Details?

To get full rule information, join with the `audit_rules` table:

```python
# Get complete violation details
violation_id = audit_note['v'][0]['id']
rule = db.query(AuditRule).filter(AuditRule.id == violation_id).first()

# Now you have:
# - rule.rule_id (e.g., "WASTE IMAGE")
# - rule.rule_name
# - rule.condition
# - rule.actions
# etc.
```
