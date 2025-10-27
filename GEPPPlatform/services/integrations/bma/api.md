# BMA Integration API Documentation

## Overview

The BMA (Bangkok Metropolitan Administration) Integration API allows external systems to create and update waste management transactions in the GEPP Platform. This API is designed to receive batch transaction data from BMA systems and automatically create or update transactions with associated material records.

## Base URL

```
/{deployment_state}/api/integration/bma
```

Where `{deployment_state}` can be:
- `dev` - Development environment
- `staging` - Staging environment
- `prod` - Production environment

## Authentication

All endpoints require JWT authentication via Bearer token in the Authorization header:

```
Authorization: Bearer <your_jwt_token>
```

The organization_id is automatically extracted from the JWT token.

---

## Endpoints

### GET /usage

Get subscription usage information for the organization.

#### Endpoint

```
GET /{deployment_state}/api/integration/bma/usage
```

#### Headers

```
Authorization: Bearer <your_jwt_token>
```

#### Response

##### Success Response (200 OK)

```json
{
  "success": true,
  "data": {
    "subscription_usage": {
      "create_transaction_limit": 100,
      "create_transaction_usage": 45,
      "ai_audit_limit": 10,
      "ai_audit_usage": 3
    }
  }
}
```

##### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `success` | Boolean | Overall success status |
| `data.subscription_usage.create_transaction_limit` | Integer | Maximum number of transactions allowed to create |
| `data.subscription_usage.create_transaction_usage` | Integer | Current number of transactions created |
| `data.subscription_usage.ai_audit_limit` | Integer | Maximum number of AI audits allowed |
| `data.subscription_usage.ai_audit_usage` | Integer | Current number of AI audits used |

##### Error Responses

###### 400 Bad Request

No active subscription found:

```json
{
  "success": false,
  "message": "No active subscription found for organization X",
  "error_code": "BAD_REQUEST"
}
```

###### 401 Unauthorized

Missing or invalid authentication:

```json
{
  "success": false,
  "message": "Missing or invalid authorization header",
  "error_code": "UNAUTHORIZED"
}
```

###### 500 Internal Server Error

Server error:

```json
{
  "success": false,
  "message": "Failed to get subscription usage: Database error",
  "error_code": "USAGE_RETRIEVAL_ERROR"
}
```

#### Usage Example

```bash
curl -X GET "https://api.gepp.com/dev/api/integration/bma/usage" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

---

### GET /audit_status

Get audit status summary for transactions in the past year.

#### Endpoint

```
GET /{deployment_state}/api/integration/bma/audit_status
```

#### Headers

```
Authorization: Bearer <your_jwt_token>
```

#### Response

##### Success Response (200 OK)

```json
{
  "success": true,
  "data": {
    "start_date": "2024-10-27",
    "num_transactions": 150,
    "ai_audit": {
      "not_audit": 45,
      "queued": 30,
      "approved": 50,
      "rejected": 25
    },
    "actual_status": {
      "pending": 60,
      "approved": 70,
      "rejected": 20
    }
  }
}
```

##### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `success` | Boolean | Overall success status |
| `data.start_date` | String | Start date for the summary (today - 1 year) in YYYY-MM-DD format |
| `data.num_transactions` | Integer | Total number of transactions in the period |
| `data.ai_audit.not_audit` | Integer | Number of transactions not yet audited by AI (ai_audit_status is null) |
| `data.ai_audit.queued` | Integer | Number of transactions queued for AI audit |
| `data.ai_audit.approved` | Integer | Number of transactions approved by AI audit |
| `data.ai_audit.rejected` | Integer | Number of transactions rejected by AI audit |
| `data.actual_status.pending` | Integer | Number of transactions with pending status |
| `data.actual_status.approved` | Integer | Number of transactions with approved status |
| `data.actual_status.rejected` | Integer | Number of transactions with rejected status |

##### Filters Applied

The summary includes transactions that meet ALL of the following criteria:
- **Organization**: Matches the authenticated user's organization
- **Date Range**: Created within the past 365 days (from today - 1 year to today)
- **Active Only**: `deleted_date` is NULL and `is_active` is true

##### Error Responses

###### 401 Unauthorized

Missing or invalid authentication:

```json
{
  "success": false,
  "message": "Missing or invalid authorization header",
  "error_code": "UNAUTHORIZED"
}
```

###### 500 Internal Server Error

Server error:

```json
{
  "success": false,
  "message": "Failed to get audit status summary: Database error",
  "error_code": "AUDIT_STATUS_RETRIEVAL_ERROR"
}
```

#### Usage Example

```bash
curl -X GET "https://api.gepp.com/dev/api/integration/bma/audit_status" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

---

### POST /add_transactions_to_audit_queue

Add all transactions with `ai_audit_status = 'null'` to the AI audit queue.

#### Endpoint

```
POST /{deployment_state}/api/integration/bma/add_transactions_to_audit_queue
```

#### Headers

```
Authorization: Bearer <your_jwt_token>
```

#### Request Body

No request body required.

#### Response

##### Success Response (200 OK)

```json
{
  "success": true,
  "data": {
    "transactions_queued": 45,
    "message": "Successfully added 45 transactions to audit queue"
  }
}
```

##### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `success` | Boolean | Overall success status |
| `data.transactions_queued` | Integer | Number of transactions added to the audit queue |
| `data.message` | String | Success message with count |

##### What This Endpoint Does

This endpoint performs a bulk update on all transactions that meet the following criteria:
- **Organization**: Matches the authenticated user's organization
- **AI Audit Status**: Currently set to `'null'` (not yet queued for audit)
- **Active Only**: `deleted_date` is NULL and `is_active` is true

**SQL Operation:**
```sql
UPDATE transactions
SET ai_audit_status = 'queued',
    updated_date = NOW()
WHERE organization_id = <your_org_id>
AND ai_audit_status = 'null'
AND deleted_date IS NULL
AND is_active = true
```

**Performance:**
- Uses optimized raw SQL for bulk updates
- Returns the count of updated transactions
- Automatically updates the `updated_date` timestamp

##### Error Responses

###### 401 Unauthorized

Missing or invalid authentication:

```json
{
  "success": false,
  "message": "Missing or invalid authorization header",
  "error_code": "UNAUTHORIZED"
}
```

###### 500 Internal Server Error

Server error:

```json
{
  "success": false,
  "message": "Failed to add transactions to audit queue: Database error",
  "error_code": "AUDIT_QUEUE_ERROR"
}
```

#### Usage Example

```bash
curl -X POST "https://api.gepp.com/dev/api/integration/bma/add_transactions_to_audit_queue" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

#### Use Cases

1. **Trigger AI Auditing**: Queue all pending transactions for AI audit processing
2. **Bulk Processing**: Efficiently update hundreds or thousands of transactions at once
3. **Workflow Integration**: Integrate with external AI audit systems that poll for queued transactions
4. **Recovery**: Re-queue transactions that were not processed due to system issues

---

### POST /transaction

Create or update transactions in batch from BMA system data.

#### Endpoint

```
POST /{deployment_state}/api/integration/bma/transaction
```

#### Headers

```
Content-Type: application/json
Authorization: Bearer <your_jwt_token>
```

#### Request Body

The request body should contain a `batch` object with the following hierarchical structure:

```json
{
  "batch": {
    "<transaction_version>": {
      "<origin_id>": {
        "<house_id>": {
          "timestamp": "<ISO_8601_datetime_with_timezone>",
          "material": {
            "<material_type>": {
              "image_url": "<url>"
            }
          }
        }
      }
    }
  }
}
```

##### Field Descriptions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `batch` | Object | Yes | Root container for all transaction data |
| `<transaction_version>` | String | Yes | Transaction version identifier (stored in `transaction.ext_id_1`) |
| `<origin_id>` | String/Integer | Yes | Origin location ID - **MUST be 2170** for BMA integration |
| `<house_id>` | String | Yes | House/building identifier (stored in `transaction.ext_id_2`) |
| `timestamp` | String | Yes | ISO 8601 datetime with timezone (e.g., "2025-10-23T10:00:00+07:00") |
| `material` | Object | Yes | Container for material data |
| `<material_type>` | String | Yes | One of: "general", "organic", "recyclable", "hazardous" |
| `image_url` | String | No | URL to the waste material image |

##### Supported Material Types

| Material Type | Material ID | Main Material ID | Category ID | Description |
|--------------|-------------|------------------|-------------|-------------|
| `general` | 94 | 11 | 4 | General Waste |
| `organic` | 77 | 10 | 3 | Food and Plant Waste |
| `recyclable` | 298 | 33 | 1 | Non-Specific Recyclables |
| `hazardous` | 113 | 25 | 5 | Non-Specific Hazardous Waste |

#### Example Request

```json
{
  "batch": {
    "v2025-Q1": {
      "2170": {
        "HOUSE-001": {
          "timestamp": "2025-10-23T08:30:00+07:00",
          "material": {
            "general": {
              "image_url": "https://s3.example.com/bma/house001-general.jpg"
            },
            "recyclable": {
              "image_url": "https://s3.example.com/bma/house001-recyclable.jpg"
            }
          }
        },
        "HOUSE-002": {
          "timestamp": "2025-10-23T09:15:00+07:00",
          "material": {
            "organic": {
              "image_url": "https://s3.example.com/bma/house002-organic.jpg"
            },
            "hazardous": {
              "image_url": "https://s3.example.com/bma/house002-hazardous.jpg"
            }
          }
        }
      }
    },
    "v2025-Q2": {
      "2170": {
        "HOUSE-003": {
          "timestamp": "2025-10-23T10:00:00+07:00",
          "material": {
            "general": {
              "image_url": "https://s3.example.com/bma/house003-general.jpg"
            }
          }
        }
      }
    }
  }
}
```

#### Response

##### Success Response (200 OK)

```json
{
  "success": true,
  "data": {
    "success": true,
    "message": "Processed 3 transactions",
    "results": {
      "processed": 3,
      "created": 2,
      "updated": 1,
      "errors": []
    },
    "subscription_usage": {
      "create_transaction_limit": 100,
      "create_transaction_usage": 45,
      "ai_audit_limit": 10,
      "ai_audit_usage": 3
    }
  }
}
```

##### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `success` | Boolean | Overall success status |
| `data.success` | Boolean | Processing success status |
| `data.message` | String | Summary message |
| `data.results.processed` | Integer | Total number of transactions processed |
| `data.results.created` | Integer | Number of new transactions created |
| `data.results.updated` | Integer | Number of existing transactions updated |
| `data.results.errors` | Array | List of errors encountered during processing |
| `data.subscription_usage.create_transaction_limit` | Integer | Maximum number of transactions allowed to create |
| `data.subscription_usage.create_transaction_usage` | Integer | Current number of transactions created (increments only on new transactions) |
| `data.subscription_usage.ai_audit_limit` | Integer | Maximum number of AI audits allowed |
| `data.subscription_usage.ai_audit_usage` | Integer | Current number of AI audits used |

##### Error Response with Partial Success (200 OK)

When some transactions succeed but others fail:

```json
{
  "success": true,
  "data": {
    "success": true,
    "message": "Processed 2 transactions",
    "results": {
      "processed": 2,
      "created": 1,
      "updated": 1,
      "errors": [
        {
          "transaction_version": "v2025-Q1",
          "house_id": "HOUSE-004",
          "error": "Invalid timestamp format"
        }
      ]
    },
    "subscription_usage": {
      "create_transaction_limit": 100,
      "create_transaction_usage": 45,
      "ai_audit_limit": 10,
      "ai_audit_usage": 3
    }
  }
}
```

##### Error Responses

###### 400 Bad Request

Missing or invalid request data:

```json
{
  "success": false,
  "message": "Missing \"batch\" field in request",
  "error_code": "BAD_REQUEST"
}
```

Transaction limit reached:

```json
{
  "success": false,
  "message": "Transaction creation limit reached. Usage: 100/100",
  "error_code": "BAD_REQUEST"
}
```

Invalid origin_id:

```json
{
  "success": false,
  "message": "Invalid origin_id. Only origin_id 2170 is allowed for BMA integration.",
  "error_code": "BAD_REQUEST"
}
```

###### 401 Unauthorized

Missing or invalid authentication:

```json
{
  "success": false,
  "message": "Missing or invalid authorization header",
  "error_code": "UNAUTHORIZED"
}
```

```json
{
  "success": false,
  "message": "Invalid token",
  "error_code": "UNAUTHORIZED"
}
```

###### 404 Not Found

Invalid route:

```json
{
  "success": false,
  "message": "Route not found",
  "error_code": "ROUTE_NOT_FOUND",
  "path": "/api/integration/bma/invalid",
  "method": "POST",
  "available_integration_routes": ["/api/integration/bma/*"]
}
```

###### 500 Internal Server Error

Server error:

```json
{
  "success": false,
  "message": "Failed to process transaction batch: Database connection error",
  "error_code": "BATCH_PROCESSING_ERROR"
}
```

---

## Business Logic

### Subscription Limits

**Transaction Creation Limits**: Each organization has a subscription with usage limits.

- `create_transaction_limit`: Maximum number of transactions allowed to create
- `create_transaction_usage`: Current number of transactions created
- **Only NEW transactions count** toward the limit (updates do not count)
- If `create_transaction_usage >= create_transaction_limit`, the API will reject the request with error: `"Transaction creation limit reached. Usage: X/Y"`
- Usage counter increments by the number of **new transactions created** in each batch
- The response always includes current subscription usage for all limits

Example:
- Batch with 5 houses: 3 new, 2 existing (updates)
- `create_transaction_usage` increases by **3** (only new transactions)
- `results.created` = 3
- `results.updated` = 2

### Origin ID Validation

**IMPORTANT**: The BMA integration **ONLY accepts origin_id = 2170**.

- All transactions must include origin_id in the batch structure
- If origin_id is not 2170, the request will be rejected with an error
- Error: `"Invalid origin_id. Only origin_id 2170 is allowed for BMA integration."`

### Transaction Matching

The API uses two fields to match existing transactions:
- `ext_id_1`: Stores the transaction version
- `ext_id_2`: Stores the house ID

For each house transaction in the batch:
1. Validate `origin_id` = 2170 (reject if not)
2. Query existing transaction with matching `ext_id_1` AND `ext_id_2` AND `organization_id`
3. If found → **Update** existing transaction
4. If not found → **Create** new transaction

### Transaction Creation

When creating a new transaction:
1. Set `ext_id_1` = transaction_version
2. Set `ext_id_2` = house_id
3. Set `origin_id` = 2170 (validated origin location)
4. Set `transaction_date` from timestamp
5. Set `transaction_method` = "origin"
6. Set `status` = "pending"
7. Create transaction_records for each material type provided
8. Link transaction_records to transaction via `transaction_records` array

### Transaction Update

When updating an existing transaction:
1. Update `transaction_date` from timestamp
2. Update `origin_id` to 2170
3. For each material in the request:
   - If transaction_record exists with matching `material_id` → **Replace** `image_url` with new data (not appended)
   - If transaction_record doesn't exist → Create new transaction_record and add to `transaction_records` array
4. **Does NOT increment** `create_transaction_usage` (only new transactions count)

### Material Records

Each material type creates a separate `transaction_record` with:
- Predefined `material_id`, `main_material_id`, and `category_id`
- `transaction_date` from the timestamp
- `quantity` = 0 (BMA doesn't provide quantity data)
- `unit` = "kg"
- `price_per_unit` = 0
- `total_price` = 0
- `images` = array containing the `image_url` (if provided)
- `status` = "pending"

---

## Usage Examples

### cURL Example

```bash
curl -X POST "https://api.gepp.com/dev/api/integration/bma/transaction" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
  -d '{
    "batch": {
      "v2025-Q1": {
        "2170": {
          "HOUSE-001": {
            "timestamp": "2025-10-23T08:30:00+07:00",
            "material": {
              "general": {
                "image_url": "https://s3.example.com/bma/house001-general.jpg"
              },
              "recyclable": {
                "image_url": "https://s3.example.com/bma/house001-recyclable.jpg"
              }
            }
          }
        }
      }
    }
  }'
```

### Python Example

```python
import requests
import json

url = "https://api.gepp.com/dev/api/integration/bma/transaction"
headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer YOUR_JWT_TOKEN"
}

payload = {
    "batch": {
        "v2025-Q1": {
            "2170": {
                "HOUSE-001": {
                    "timestamp": "2025-10-23T08:30:00+07:00",
                    "material": {
                        "general": {
                            "image_url": "https://s3.example.com/bma/house001-general.jpg"
                        },
                        "recyclable": {
                            "image_url": "https://s3.example.com/bma/house001-recyclable.jpg"
                        }
                    }
                }
            }
        }
    }
}

response = requests.post(url, headers=headers, json=payload)
print(response.json())
```

### JavaScript Example

```javascript
const url = 'https://api.gepp.com/dev/api/integration/bma/transaction';
const token = 'YOUR_JWT_TOKEN';

const payload = {
  batch: {
    'v2025-Q1': {
      '2170': {
        'HOUSE-001': {
          timestamp: '2025-10-23T08:30:00+07:00',
          material: {
            general: {
              image_url: 'https://s3.example.com/bma/house001-general.jpg'
            },
            recyclable: {
              image_url: 'https://s3.example.com/bma/house001-recyclable.jpg'
            }
          }
        }
      }
    }
  }
};

fetch(url, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`
  },
  body: JSON.stringify(payload)
})
  .then(response => response.json())
  .then(data => console.log(data))
  .catch(error => console.error('Error:', error));
```

---

## Notes

### Timestamp Format
- Must be ISO 8601 format with timezone
- Example: `2025-10-23T08:30:00+07:00`
- If parsing fails, current server time will be used as fallback

### Image URLs
- Optional but recommended
- Should be publicly accessible URLs or pre-signed URLs
- When updating an existing transaction with the same material_id, the new image URL **replaces** the old one (not appended)
- Images are stored as JSONB array in the database

### Transaction Versioning
- Use meaningful version identifiers (e.g., "v2025-Q1", "2025-10-23", "batch-001")
- Same version + house_id combination will update the same transaction

### Organization Scope
- All transactions are scoped to the organization_id from the JWT token
- Users can only create/update transactions within their organization

### Error Handling
- Errors in individual house transactions won't fail the entire batch
- Check the `errors` array in the response for details on failed transactions
- Database transactions are rolled back only on complete batch failure

---

## Changelog

### v1.1.0 (2025-10-27)
- Added subscription usage limits
- Added GET `/usage` endpoint to check subscription limits
- Added GET `/audit_status` endpoint to get transaction audit status summary for the past year
- Added POST `/add_transactions_to_audit_queue` endpoint to bulk queue transactions for AI audit
- Added `audit_date` and `ai_audit_date` timestamp columns to track when audits were performed
- `create_transaction_usage` increments only for new transactions (updates don't count)
- Response now includes `subscription_usage` with all limits and current usage
- API rejects requests when transaction limit is reached
- Image URLs are now replaced (not appended) when updating existing material records
- All records use organization owner's ID for `created_by_id`

### v1.0.0 (2025-10-23)
- Initial release
- POST /transaction endpoint
- Support for 4 material types (general, organic, recyclable, hazardous)
- Batch processing with partial error handling
- Origin ID validation (only 2170 allowed)
