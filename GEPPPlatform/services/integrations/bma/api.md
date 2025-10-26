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
2. For each material in the request:
   - If transaction_record exists with matching `material_id` → Append new `image_url` to existing images
   - If transaction_record doesn't exist → Create new transaction_record and add to `transaction_records` array

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
- Multiple images can be added to the same material by sending multiple requests
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

### v1.0.0 (2025-10-23)
- Initial release
- POST /transaction endpoint
- Support for 4 material types (general, organic, recyclable, hazardous)
- Batch processing with partial error handling
