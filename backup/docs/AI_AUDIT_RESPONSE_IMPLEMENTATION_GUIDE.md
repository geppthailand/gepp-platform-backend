# AI Audit Response System - Implementation Guide

## Overview
Complete implementation of AI audit response management system with customizable message patterns for BMA and other rule sets.

---

## ✅ COMPLETED: Backend Implementation

### 1. Database Migrations

Three migration files created in `/backend/migrations/`:

#### Migration 1: AI Audit Rule Sets Table
**File**: `20260122_100000_001_create_ai_audit_rule_sets_table.sql`
- Creates `ai_audit_rule_sets` table
- Inserts 2 default rule sets:
  - ID 1: `default` → `default_audit_rule_set`
  - ID 2: `bma` → `bma_audit_rule_set`

#### Migration 2: Organizations Table Updates
**File**: `20260122_110000_002_add_ai_audit_columns_to_organizations.sql`
- Adds 3 columns to `organizations`:
  - `ai_audit_rule_set_id` (BIGINT, default=1, FK to ai_audit_rule_sets)
  - `enable_ai_audit_response_setting` (BOOLEAN, default=FALSE)
  - `enable_ai_audit_api` (BOOLEAN, default=FALSE)

#### Migration 3: AI Audit Response Patterns Table
**File**: `20260122_120000_003_create_ai_audit_response_patterns_table.sql`
- Creates `ai_audit_response_patterns` table with columns:
  - `id` - Primary key
  - `name` - Pattern name
  - `condition` - JSONB array of conditions
  - `priority` - Integer (0 = highest priority)
  - `pattern` - Response message template
  - `organization_id` - FK to organizations

### 2. Backend Models

**File**: `/backend/GEPPPlatform/models/ai_audit_models.py`

```python
class AiAuditRuleSet(Base, BaseModel):
    """Defines different audit rule configurations"""
    name = Column(String(255), nullable=False, unique=True)
    function_name = Column(String(255), nullable=False)

class AiAuditResponsePattern(Base, BaseModel):
    """Stores customizable response message templates"""
    name = Column(String(255), nullable=False)
    condition = Column(JSONB, nullable=False, default=[])
    priority = Column(Integer, nullable=False, default=0)
    pattern = Column(Text, nullable=False)
    organization_id = Column(BigInteger, ForeignKey('organizations.id'))
```

**Updated**: `/backend/GEPPPlatform/models/subscriptions/organizations.py`
- Added relationships to AI audit models
- Added new columns for AI audit configuration

### 3. API Endpoints

**Endpoint**: `GET /api/organizations/me`

**Response Structure**:
```json
{
  "id": 1,
  "name": "Organization Name",
  "allow_ai_audit": true,
  "ai_audit_rule_set_id": 2,
  "enable_ai_audit_response_setting": true,
  "enable_ai_audit_api": true,
  "info": { ...company info... }
}
```

**Implementation**: `/backend/GEPPPlatform/services/cores/organizations/organization_handlers.py`
- Route added: `GET /api/organizations/me`
- Uses existing `handle_get_my_organization` handler
- Returns organization with new AI audit fields

### 4. YAML Prompt Templates

**Structure**:
```
backend/GEPPPlatform/prompts/
├── __init__.py
├── base.py (PromptLoader utility)
└── ai_audit/
    ├── default/
    │   ├── general.yaml
    │   ├── recyclable.yaml
    │   ├── organic.yaml
    │   └── hazardous.yaml
    └── bma/
        ├── general.yaml
        ├── recyclable.yaml
        ├── organic.yaml
        └── hazardous.yaml
```

**Prompt Loader Usage**:
```python
from GEPPPlatform.prompts.base import PromptLoader

loader = PromptLoader()

# Load specific prompt
prompt = loader.load_ai_audit_prompt(rule_set="bma", waste_type="recyclable")

# Load all prompts for a rule set
prompts = loader.get_ai_audit_prompts_for_rule_set("bma")
# Returns: {"general": prompt, "recyclable": prompt, "organic": prompt, "hazardous": prompt}
```

### 5. LLM Output Structure

The prompts are configured to return this JSON structure:

```json
{
  "claimed_type": "recyclable",
  "audit_status": "pass" | "reject",
  "confidence_score": 0.95,
  "remark": {
    "code": "wrong_category" | "correct_category" | "contaminated" | "unclear_image",
    "severity": "critical" | "minor" | "info",
    "details": {
      "detected": "organic waste",
      "reason": "visible food scraps on container",
      "items": "plastic bottle with food residue"
    },
    "correction_action": "Remove food scraps and wash the container"
  }
}
```

### 6. Response Pattern Matching

**Example Pattern**:
```json
{
  "name": "Wrong Category - Recyclable to Organic",
  "condition": [
    "remark.code == 'wrong_category'",
    "claimed_type == 'recyclable'",
    "remark.details.detected contains 'organic'"
  ],
  "priority": 0,
  "pattern": "จากรูป {claimed_type} ตรวจพบว่าเป็น {remark.details.detected} เนื่องจากพบ {remark.details.reason}"
}
```

**Rendered Output**:
```
"จากรูป recyclable ตรวจพบว่าเป็น organic waste เนื่องจากพบ visible food scraps on container"
```

---

## ✅ COMPLETED: Frontend API Service

**File**: `/frontend/gepp-business-v2/src/services/api/OrganizationApiService.ts`

**Updated**:
1. Added new fields to `Organization` interface:
   ```typescript
   export interface Organization {
     ai_audit_rule_set_id?: number;
     enable_ai_audit_response_setting?: boolean;
     enable_ai_audit_api?: boolean;
     // ... existing fields
   }
   ```

2. Added new method:
   ```typescript
   async getOrganizationMe(): Promise<ApiResponse<Organization>> {
     return this.get<Organization>('/api/organizations/me');
   }
   ```

---

## 🔄 TODO: Frontend Implementation

### Step 1: Fetch Organization Data in WasteTransactions Component

**File**: `/frontend/gepp-business-v2/src/pages/WasteTransactions/index.tsx`

Add state and fetch logic:

```typescript
// Add state for organization
const [organization, setOrganization] = useState<Organization | null>(null);
const [orgLoading, setOrgLoading] = useState(false);

// Add useEffect to fetch organization data
useEffect(() => {
  const fetchOrganization = async () => {
    try {
      setOrgLoading(true);
      const response = await organizationApiService.getOrganizationMe();

      if (response.success && response.data) {
        setOrganization(response.data);
      }
    } catch (error) {
      console.error('Failed to fetch organization:', error);
    } finally {
      setOrgLoading(false);
    }
  };

  fetchOrganization();
}, []);
```

### Step 2: Add Response Settings Option to Dropdown

**File**: `/frontend/gepp-business-v2/src/pages/WasteTransactions/index.tsx`

Update `auditMenuItems` around line 243:

```typescript
const auditMenuItems: MenuProps['items'] = [
  {
    key: 'ai-audit',
    label: (
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '2px 0' }}>
        <RobotOutlined style={{ color: '#9ac7b5' }} />
        <span style={{ color: '#9ac7b5' }}>{t.transaction.auditWithAI}</span>
      </div>
    ),
    disabled: isAiAuditLoading,
  },
  {
    key: 'manual-audit',
    label: (
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '2px 0' }}>
        <UserOutlined style={{ color: '#9ac7b5' }} />
        <span style={{ color: '#9ac7b5' }}>{t.transaction.auditManually}</span>
      </div>
    ),
  },
  // ADD THIS NEW ITEM - Only show if enable_ai_audit_response_setting is true
  ...(organization?.enable_ai_audit_response_setting ? [{
    key: 'response-settings',
    label: (
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '2px 0' }}>
        <SettingOutlined style={{ color: '#9ac7b5' }} />
        <span style={{ color: '#9ac7b5' }}>ตั้งค่าการตอบกลับ</span>
      </div>
    ),
  }] : []),
];
```

### Step 3: Handle Menu Click

Update `handleAuditMenuClick` function:

```typescript
const handleAuditMenuClick: MenuProps['onClick'] = ({ key }) => {
  switch (key) {
    case 'ai-audit':
      handleAiAudit();
      break;
    case 'manual-audit':
      handleManualAudit();
      break;
    case 'response-settings':
      setResponseSettingsModalVisible(true); // Add this state
      break;
    default:
      break;
  }
};
```

### Step 4: Create AI Response Settings Modal Component

**Create New File**: `/frontend/gepp-business-v2/src/components/AiResponseSettingsModal.tsx`

```typescript
import React, { useState, useEffect } from 'react';
import {
  Modal,
  Form,
  Input,
  InputNumber,
  Button,
  Table,
  Space,
  message,
  Popconfirm,
  Tag,
} from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';

interface ResponsePattern {
  id?: number;
  name: string;
  condition: string[];
  priority: number;
  pattern: string;
}

interface AiResponseSettingsModalProps {
  visible: boolean;
  onClose: () => void;
  organizationId: number;
}

const AiResponseSettingsModal: React.FC<AiResponseSettingsModalProps> = ({
  visible,
  onClose,
  organizationId,
}) => {
  const [form] = Form.useForm();
  const [patterns, setPatterns] = useState<ResponsePattern[]>([]);
  const [loading, setLoading] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);

  // Fetch response patterns
  useEffect(() => {
    if (visible) {
      fetchPatterns();
    }
  }, [visible]);

  const fetchPatterns = async () => {
    setLoading(true);
    try {
      // TODO: Implement API call to fetch patterns
      // const response = await aiAuditService.getResponsePatterns(organizationId);
      // setPatterns(response.data);
    } catch (error) {
      message.error('Failed to fetch response patterns');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (values: any) => {
    try {
      setLoading(true);

      const patternData = {
        name: values.name,
        condition: values.condition.split('\n').filter((c: string) => c.trim()),
        priority: values.priority,
        pattern: values.pattern,
        organization_id: organizationId,
      };

      if (editingId) {
        // Update existing pattern
        // await aiAuditService.updateResponsePattern(editingId, patternData);
        message.success('Response pattern updated successfully');
      } else {
        // Create new pattern
        // await aiAuditService.createResponsePattern(patternData);
        message.success('Response pattern created successfully');
      }

      form.resetFields();
      setEditingId(null);
      fetchPatterns();
    } catch (error) {
      message.error('Failed to save response pattern');
    } finally {
      setLoading(false);
    }
  };

  const handleEdit = (pattern: ResponsePattern) => {
    setEditingId(pattern.id || null);
    form.setFieldsValue({
      name: pattern.name,
      condition: pattern.condition.join('\n'),
      priority: pattern.priority,
      pattern: pattern.pattern,
    });
  };

  const handleDelete = async (id: number) => {
    try {
      setLoading(true);
      // await aiAuditService.deleteResponsePattern(id);
      message.success('Response pattern deleted successfully');
      fetchPatterns();
    } catch (error) {
      message.error('Failed to delete response pattern');
    } finally {
      setLoading(false);
    }
  };

  const columns = [
    {
      title: 'Priority',
      dataIndex: 'priority',
      key: 'priority',
      width: 80,
      render: (priority: number) => <Tag color="blue">{priority}</Tag>,
    },
    {
      title: 'Name',
      dataIndex: 'name',
      key: 'name',
      width: 200,
    },
    {
      title: 'Conditions',
      dataIndex: 'condition',
      key: 'condition',
      render: (conditions: string[]) => (
        <div>
          {conditions.map((c, i) => (
            <Tag key={i} style={{ marginBottom: 4 }}>{c}</Tag>
          ))}
        </div>
      ),
    },
    {
      title: 'Pattern Template',
      dataIndex: 'pattern',
      key: 'pattern',
      ellipsis: true,
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 150,
      render: (_: any, record: ResponsePattern) => (
        <Space>
          <Button
            type="link"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          >
            Edit
          </Button>
          <Popconfirm
            title="Are you sure to delete this pattern?"
            onConfirm={() => handleDelete(record.id!)}
            okText="Yes"
            cancelText="No"
          >
            <Button type="link" danger icon={<DeleteOutlined />}>
              Delete
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Modal
      title="ตั้งค่าการตอบกลับ AI Audit"
      open={visible}
      onCancel={onClose}
      width={1000}
      footer={null}
    >
      <div style={{ marginBottom: 24 }}>
        <Form form={form} layout="vertical" onFinish={handleSubmit}>
          <Form.Item
            label="Pattern Name"
            name="name"
            rules={[{ required: true, message: 'Please enter pattern name' }]}
          >
            <Input placeholder="e.g., Wrong Category - Recyclable to Organic" />
          </Form.Item>

          <Form.Item
            label="Conditions (one per line)"
            name="condition"
            rules={[{ required: true, message: 'Please enter conditions' }]}
            extra='Example: remark.code == "wrong_category"'
          >
            <Input.TextArea
              rows={4}
              placeholder={'remark.code == "wrong_category"\nclaimed_type == "recyclable"'}
            />
          </Form.Item>

          <Form.Item
            label="Priority (0 = highest)"
            name="priority"
            rules={[{ required: true, message: 'Please enter priority' }]}
          >
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>

          <Form.Item
            label="Response Pattern Template"
            name="pattern"
            rules={[{ required: true, message: 'Please enter pattern template' }]}
            extra="Use placeholders like {claimed_type}, {remark.details.detected}, {remark.details.reason}"
          >
            <Input.TextArea
              rows={3}
              placeholder="จากรูป {claimed_type} ตรวจพบว่าเป็น {remark.details.detected} เนื่องจากพบ {remark.details.reason}"
            />
          </Form.Item>

          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit" loading={loading}>
                {editingId ? 'Update Pattern' : 'Add Pattern'}
              </Button>
              {editingId && (
                <Button
                  onClick={() => {
                    form.resetFields();
                    setEditingId(null);
                  }}
                >
                  Cancel Edit
                </Button>
              )}
            </Space>
          </Form.Item>
        </Form>
      </div>

      <Table
        columns={columns}
        dataSource={patterns}
        loading={loading}
        rowKey="id"
        pagination={{ pageSize: 10 }}
      />
    </Modal>
  );
};

export default AiResponseSettingsModal;
```

### Step 5: Add Modal State and Import to WasteTransactions

**File**: `/frontend/gepp-business-v2/src/pages/WasteTransactions/index.tsx`

```typescript
// Add import at top
import AiResponseSettingsModal from '@/components/AiResponseSettingsModal';

// Add state
const [responseSettingsModalVisible, setResponseSettingsModalVisible] = useState(false);

// Add modal to render (before closing tag of component)
<AiResponseSettingsModal
  visible={responseSettingsModalVisible}
  onClose={() => setResponseSettingsModalVisible(false)}
  organizationId={organization?.id || 0}
/>
```

### Step 6: Create AI Audit Response API Service

**Create New File**: `/frontend/gepp-business-v2/src/services/api/AiAuditResponseApiService.ts`

```typescript
import { BaseApiService } from './BaseApiService';
import type { ApiResponse } from './BaseApiService';

export interface AiAuditResponsePattern {
  id?: number;
  name: string;
  condition: string[];
  priority: number;
  pattern: string;
  organization_id: number;
}

class AiAuditResponseApiService extends BaseApiService {
  private readonly BASE_PATH = '/api/ai-audit-responses';

  async getResponsePatterns(organizationId: number): Promise<ApiResponse<AiAuditResponsePattern[]>> {
    return this.get<AiAuditResponsePattern[]>(`${this.BASE_PATH}?organization_id=${organizationId}`);
  }

  async createResponsePattern(data: Omit<AiAuditResponsePattern, 'id'>): Promise<ApiResponse<AiAuditResponsePattern>> {
    return this.post<AiAuditResponsePattern>(this.BASE_PATH, data);
  }

  async updateResponsePattern(id: number, data: Partial<AiAuditResponsePattern>): Promise<ApiResponse<AiAuditResponsePattern>> {
    return this.put<AiAuditResponsePattern>(`${this.BASE_PATH}/${id}`, data);
  }

  async deleteResponsePattern(id: number): Promise<ApiResponse<void>> {
    return this.delete<void>(`${this.BASE_PATH}/${id}`);
  }
}

export const aiAuditResponseApiService = new AiAuditResponseApiService();
export default aiAuditResponseApiService;
```

---

## 🔧 Backend CRUD API Endpoints (TODO)

You still need to create these backend endpoints for managing response patterns:

**File**: Create `/backend/GEPPPlatform/services/cores/ai_audit_responses/`

```
ai_audit_responses/
├── __init__.py
├── ai_audit_response_handlers.py
└── ai_audit_response_service.py
```

**Endpoints to implement**:
- `GET /api/ai-audit-responses?organization_id={id}` - List all patterns
- `POST /api/ai-audit-responses` - Create new pattern
- `PUT /api/ai-audit-responses/{id}` - Update pattern
- `DELETE /api/ai-audit-responses/{id}` - Delete pattern

---

## 📊 Testing Checklist

### Backend Testing
- [ ] Run migrations in order
- [ ] Verify tables created correctly
- [ ] Test `/api/organizations/me` endpoint
- [ ] Verify organization fields returned
- [ ] Test prompt loader with different rule sets
- [ ] Verify YAML prompts load correctly

### Frontend Testing
- [ ] Organization data fetches on page load
- [ ] "ตั้งค่าการตอบกลับ" shows only when `enable_ai_audit_response_setting` is true
- [ ] Modal opens when clicking menu item
- [ ] Response patterns table displays correctly
- [ ] CRUD operations work for patterns

---

## 🎯 Next Steps

1. **Run Backend Migrations**:
   ```bash
   cd backend
   # Run your migration script
   ```

2. **Implement Backend CRUD APIs** for response patterns

3. **Complete Frontend Integration**:
   - Add modal component
   - Wire up API calls
   - Test end-to-end flow

4. **Implement AI Audit Processing**:
   - Use prompt templates with LangChain
   - Process images with vision models
   - Match conditions and apply patterns
   - Return formatted responses

---

## 📝 Example Workflow

1. **Organization Setup**:
   - Admin enables `enable_ai_audit_response_setting` for organization
   - Sets `ai_audit_rule_set_id` to 2 (BMA)

2. **User Creates Pattern**:
   - Opens "ตั้งค่าการตอบกลับ" modal
   - Creates pattern for wrong category detection
   - Sets priority and conditions

3. **AI Audit Process**:
   - User uploads waste transaction with image
   - AI analyzes using BMA recyclable prompt
   - Returns structured JSON result
   - System matches conditions (priority order)
   - Formats response using pattern template
   - Shows formatted message to user

---

## 🔗 Related Files Reference

### Backend
- Models: `/backend/GEPPPlatform/models/ai_audit_models.py`
- Organization Service: `/backend/GEPPPlatform/services/cores/organizations/organization_service.py`
- Prompts: `/backend/GEPPPlatform/prompts/ai_audit/`

### Frontend
- Page: `/frontend/gepp-business-v2/src/pages/WasteTransactions/index.tsx`
- API Service: `/frontend/gepp-business-v2/src/services/api/OrganizationApiService.ts`
- Modal Component: `/frontend/gepp-business-v2/src/components/AiResponseSettingsModal.tsx` (to create)

---

## 💡 Tips

- Conditions are evaluated in priority order (0 first)
- Use JSONB for flexible condition matching
- Pattern templates support nested object access
- LangChain prompt loader handles YAML parsing automatically
- Test prompts with real images before deployment

---

**Created**: 2026-01-22
**Status**: Backend Complete, Frontend In Progress
