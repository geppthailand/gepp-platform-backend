# AI Audit System Simplification - Implementation Guide

**Date:** 2026-01-29
**Status:** Backend Complete, Frontend Pending Manual Updates

---

## Summary of Changes

This document outlines the comprehensive simplification of the BMA AI Audit system, including database schema changes, backend logic updates, and required frontend modifications.

---

## 1. Database Schema Changes

### Migration File
**Location:** `backend/migrations/20260129_140000_004_simplify_ai_audit_response_patterns.sql`

### Key Changes
1. **Simplified `condition` field** in `ai_audit_response_patterns` table:
   - **Before:** `JSONB` array of complex condition expressions
   - **After:** `VARCHAR(50)` containing single audit code

2. **Updated `priority` default:**
   - **Before:** Default `0` (highest priority)
   - **After:** Default `1000` (fixed, not used for priority sorting in BMA)

3. **Available Codes:**
   ```
   ncm - non_complete_material (critical)
   cc  - correct_category (info)
   wc  - wrong_category (critical)
   ui  - unclear_image (critical)
   hc  - heavy_contamination (critical)
   lc  - light_contamination (minor)
   pe  - parse_error (critical)
   ie  - image_error (critical)
   ```

---

## 2. Backend Model Updates

### File: `backend/GEPPPlatform/models/ai_audit_models.py`

**Updated `AiAuditResponsePattern` model:**
```python
class AiAuditResponsePattern(Base, BaseModel):
    """
    Available placeholders:
    - {{code}}: The audit code (e.g., "wc", "cc")
    - {{detect_type}}: Detected material type name (e.g., "ขยะอินทรีย์", "ขยะรีไซเคิล")
    - {{claimed_type}}: Claimed material type name (e.g., "ขยะทั่วไป", "ขยะรีไซเคิล")
    - {{warning_items}}: Comma-separated list of wrong items (Thai names)
    """
    condition = Column(String(50), nullable=False, default='cc')  # Simplified
    priority = Column(Integer, nullable=False, default=1000)  # Fixed priority
    pattern = Column(Text, nullable=False)  # Template with {{placeholder}}
```

---

## 3. Backend Audit Logic - Complete Rewrite

### File: `backend/GEPPPlatform/services/custom/functions/ai_audit_v1/bma_audit_rule_set.py`

### New Features Implemented

#### A. Database Saving
- Results are now saved directly to `transactions.ai_audit_note`
- Token usage is split and saved to `transactions.audit_tokens`
- `ai_audit_status` is updated (`approved` or `rejected`)
- `ai_audit_date` is recorded

#### B. Custom Message Function
```python
def _get_custom_message(
    db_session: Session,
    organization_id: int,
    code: str,
    detect_type_id: int,
    claimed_type_id: int,
    warning_items: List[str]
) -> str
```

**Logic:**
1. Query `ai_audit_response_patterns` table by `organization_id` and `code`
2. Replace placeholders: `{{code}}`, `{{detect_type}}`, `{{claimed_type}}`, `{{warning_items}}`
3. Return formatted custom message
4. Falls back to `รหัสผล: {code}` if no pattern found

#### C. Simplified Response Format
**New Structure:**
```json
{
  "2025-01": {
    "เขตยานนาวา": {
      "แขวงช่องนนทรี": {
        "0000000000001": {
          "status": "approve|reject",
          "message": "รูปภาพประเภทวัสดุไม่ครบถ้วนขาด ...",
          "materials": {
            "general": {
              "image_url": "https://...",
              "detect": "general",
              "status": "approve",
              "message": "custom_message from pattern"
            },
            "organic": {...},
            "recyclable": {...},
            "hazardous": {...}
          }
        }
      }
    }
  }
}
```

**Transaction Status Logic:**
- `status = "reject"` if:
  - Step 1 failed (missing required materials), OR
  - Any material in Step 2 is rejected
- `status = "approve"` if:
  - Step 1 passed AND all materials approved

**Message Logic:**
- If Step 1 failed: `"รูปภาพประเภทวัสดุไม่ครบถ้วนขาด {missing_items}"`
- If Step 1 passed: `""` (empty string)

#### D. Material Type Mappings
```python
MATERIAL_ID_TO_THAI: Dict[int, str] = {
    94: "ขยะทั่วไป",
    77: "ขยะอินทรีย์",
    298: "ขยะรีไซเคิล",
    113: "ขยะอันตราย",
}
```

---

## 4. Frontend Updates Required

### A. API Service Type Updates ✅ COMPLETED

**File:** `frontend/gepp-business-v2/src/services/api/AiAuditResponseApiService.ts`

**Changed:**
```typescript
// Before
export type AiAuditResponsePattern = {
  condition: string[];  // Array
  priority: number;
};

// After
export type AiAuditResponsePattern = {
  condition: string;  // Single code string
  priority: number;
};
```

### B. Modal Component Updates ⚠️ PENDING

**File:** `frontend/gepp-business-v2/src/components/AiResponseSettingsModal.tsx`

**Required Changes:**

1. **Add Select Component Import:**
   ```typescript
   import { ..., Select, ... } from 'antd';
   ```

2. **Add Audit Code Options:**
   ```typescript
   const AUDIT_CODE_OPTIONS = [
     { value: 'ncm', label: 'ncm - ไม่ครบถ้วน', severity: 'critical' },
     { value: 'cc', label: 'cc - ถูกต้อง', severity: 'info' },
     { value: 'wc', label: 'wc - ผิดประเภท', severity: 'critical' },
     { value: 'ui', label: 'ui - ภาพไม่ชัด', severity: 'critical' },
     { value: 'hc', label: 'hc - เปื้อนหนัก', severity: 'critical' },
     { value: 'lc', label: 'lc - เปื้อนเล็กน้อย', severity: 'minor' },
     { value: 'pe', label: 'pe - ข้อผิดพลาด', severity: 'critical' },
     { value: 'ie', label: 'ie - ข้อผิดพลาดในภาพ', severity: 'critical' },
   ];
   ```

3. **Replace Condition TextArea with Select Dropdown:**
   ```typescript
   // Remove old TextArea for condition input
   // Replace with:
   <Form.Item
     label="รหัสเงื่อนไข"
     name="condition"
     rules={[{ required: true, message: 'กรุณาเลือกรหัสเงื่อนไข' }]}
   >
     <Select
       placeholder="เลือกรหัสเงื่อนไข"
       options={AUDIT_CODE_OPTIONS}
     />
   </Form.Item>
   ```

4. **Remove Priority Input Field:**
   ```typescript
   // Remove the InputNumber for priority
   // Set priority=1000 automatically in handleSubmit
   const patternData = {
     name: values.name,
     condition: values.condition,  // Now single string
     priority: 1000,  // Fixed value
     pattern: values.pattern,
     organization_id: organizationId,
   };
   ```

5. **Update handleEdit Function:**
   ```typescript
   const handleEdit = (pattern: AiAuditResponsePattern) => {
     setEditingId(pattern.id || null);
     form.setFieldsValue({
       name: pattern.name,
       condition: pattern.condition,  // Single string, not array
       pattern: pattern.pattern,
     });
   };
   ```

6. **Update Table Columns:**
   ```typescript
   // Update "เงื่อนไข" column to show single code tag
   {
     title: 'รหัสเงื่อนไข',
     dataIndex: 'condition',
     key: 'condition',
     render: (code: string) => (
       <Tag color={getCodeColor(code)}>
         {getCodeLabel(code)}
       </Tag>
     ),
   }
   ```

7. **Remove "ลำดับความสำคัญ" Column:**
   ```typescript
   // Remove priority column from table columns array
   ```

### C. Documentation Modal Updates ⚠️ PENDING

**Update Available Parameters Table:**

Replace old parameters with:
```typescript
const AVAILABLE_PARAMS = [
  { param: '{{code}}', desc: 'รหัสผลการตรวจสอบ', example: 'wc, cc, ui' },
  { param: '{{detect_type}}', desc: 'ประเภทที่ AI ตรวจพบ (ภาษาไทย)', example: 'ขยะอินทรีย์' },
  { param: '{{claimed_type}}', desc: 'ประเภทที่ผู้ใช้อ้าง (ภาษาไทย)', example: 'ขยะรีไซเคิล' },
  { param: '{{warning_items}}', desc: 'รายการที่มีปัญหา', example: 'ขวดพลาสติก, กล่องกระดาษ' },
];
```

**Simplify Documentation Content:**
- Remove complex logical operators section (==, !=, contains, etc.)
- Remove old remark codes (wrong_category, recyclable_dirty, etc.)
- Add simple audit code list with Thai descriptions
- Update example patterns to use new placeholders

**Example Pattern Section:**
```typescript
<div>
  <Text strong>ตัวอย่างที่ 1: ตรวจพบประเภทผิด (wc)</Text>
  <Code>
    จากรูป {{claimed_type}} ตรวจพบว่าเป็น {{detect_type}}
    พบสิ่งของที่ไม่ถูกต้อง: {{warning_items}}
  </Code>
  <Text type="secondary">
    → ผลลัพธ์: จากรูป ขยะรีไซเคิล ตรวจพบว่าเป็น ขยะอินทรีย์
    พบสิ่งของที่ไม่ถูกต้อง: เศษผัก, เปลือกผลไม้
  </Text>
</div>
```

---

## 5. API Response Structure

### Before (Old Format)
```json
{
  "success": true,
  "results": [
    {
      "transaction_id": 123,
      "step_1": {...},
      "step_2": [...]
    }
  ]
}
```

### After (New Format)
```json
{
  "success": true,
  "rule_set": "bma_audit_rule_set",
  "organization_id": 8,
  "total_transactions": 1,
  "token_usage": {
    "input_tokens": 15234,
    "output_tokens": 512,
    "total_tokens": 15746
  },
  "results": {
    "2025-01": {
      "เขตยานนาวา": {
        "แขวงช่องนนทรี": {
          "0000000000001": {
            "status": "approve",
            "message": "",
            "materials": {
              "general": {
                "image_url": "https://...",
                "detect": "general",
                "status": "approve",
                "message": "ขยะทั่วไปถูกต้อง"
              }
            }
          }
        }
      }
    }
  }
}
```

---

## 6. Database Schema After Migration

```sql
-- ai_audit_response_patterns table
CREATE TABLE ai_audit_response_patterns (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    condition VARCHAR(50) NOT NULL DEFAULT 'cc',  -- Simplified!
    priority INTEGER NOT NULL DEFAULT 1000,       -- Fixed value
    pattern TEXT NOT NULL,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    created_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMPTZ,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);
```

---

## 7. Testing Checklist

### Backend ✅
- [x] Migration runs successfully
- [x] `AiAuditResponsePattern` model updated
- [x] `_get_custom_message()` function implemented
- [x] Simplified response format implemented
- [x] Database saving (ai_audit_note, audit_tokens) implemented
- [x] Parallel processing maintained

### Frontend ⚠️ MANUAL TESTING REQUIRED
- [ ] Type definitions updated in API service
- [ ] Modal uses dropdown for code selection
- [ ] Priority field removed from form
- [ ] Table columns updated
- [ ] Documentation modal simplified
- [ ] Pattern creation/editing works with new format
- [ ] Pattern display shows correct code labels

---

## 8. Migration Instructions

### Step 1: Run Database Migration
```bash
cd backend/migrations
psql -U your_user -d your_database -f 20260129_140000_004_simplify_ai_audit_response_patterns.sql
```

### Step 2: Update Requirements (if needed)
```bash
cd backend
pip install -r requirements.txt
```

### Step 3: Test Backend
```bash
# Test with sample transaction IDs
python -m pytest tests/test_bma_audit_v1.py  # If test file exists
```

### Step 4: Update Frontend
```bash
cd frontend/gepp-business-v2
npm install  # If dependencies changed
npm run dev
```

### Step 5: Manual Frontend Updates
Apply changes listed in Section 4.B and 4.C above.

---

## 9. Rollback Plan

If issues occur, rollback using:
```sql
-- Revert condition column to JSONB
ALTER TABLE ai_audit_response_patterns
ALTER COLUMN condition TYPE JSONB USING condition::text::jsonb;

-- Revert priority default
ALTER TABLE ai_audit_response_patterns
ALTER COLUMN priority SET DEFAULT 0;
```

---

## 10. Contact

For questions or issues:
- Backend: Check `bma_audit_rule_set.py`
- Frontend: Check `AiResponseSettingsModal.tsx`
- Database: Check migration file

---

**Implementation Status:** Backend Complete ✅ | Frontend Pending ⚠️

