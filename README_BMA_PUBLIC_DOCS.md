# BMA Public Documentation

## Overview

Hash-protected, filtered Swagger documentation specifically for BMA (Bangkok Metropolitan Administration) integration partners. This documentation includes only the essential endpoints needed for external integration, maintaining security while providing necessary API information.

## Access URLs

### Development Environment
- **Swagger UI**: `https://api.geppdata.com/dev/docs/bma/0a70bf9ef2fcb7c2dc6c2b046ebb052c`
- **OpenAPI JSON**: `https://api.geppdata.com/dev/docs/bma/0a70bf9ef2fcb7c2dc6c2b046ebb052c/openapi.json`

### Staging Environment
- **Swagger UI**: `https://api.geppdata.com/staging/docs/bma/0a70bf9ef2fcb7c2dc6c2b046ebb052c`
- **OpenAPI JSON**: `https://api.geppdata.com/staging/docs/bma/0a70bf9ef2fcb7c2dc6c2b046ebb052c/openapi.json`

### Production Environment
- **Swagger UI**: `https://api.geppdata.com/prod/docs/bma/0a70bf9ef2fcb7c2dc6c2b046ebb052c`
- **OpenAPI JSON**: `https://api.geppdata.com/prod/docs/bma/0a70bf9ef2fcb7c2dc6c2b046ebb052c/openapi.json`

## Included Endpoints

The BMA public documentation includes only these 6 endpoints:

### 1. Authentication
- **POST** `/api/auth/integration` - Obtain integration token (7-day validity)

### 2. Transaction Management
- **GET** `/api/integration/bma/transaction` - List transactions with pagination
  - Query parameters: `limit`, `page`, `transaction_version`, `origin_id`
  - Sorted by house_id (ext_id_2) ascending

- **POST** `/api/integration/bma/transaction` - Submit batch transactions
  - Batch upload of waste transactions with images

- **GET** `/api/integration/bma/transaction/{transaction_version}/{house_id}` - Get specific transaction
  - Retrieve single transaction by version and house ID

### 3. Monitoring
- **GET** `/api/integration/bma/audit_status` - Check AI audit processing status
  - Monitor audit queue and completion status

- **GET** `/api/integration/bma/usage` - View API usage statistics
  - Track API calls and transaction counts

## Features

### Security
- **Hash-Protected URL**: Uses secure hash `0a70bf9ef2fcb7c2dc6c2b046ebb052c` in URL path
- **No Authentication Required**: Documentation is publicly accessible via hash
- **Filtered Content**: Only shows BMA-specific endpoints, internal APIs are hidden

### Branding
- **BMA Green Theme**: Custom color scheme (#1b5e20) for BMA branding
- **Custom Title**: "GEPP Platform - BMA Integration API"
- **BMA-Specific Documentation**: Integration workflow and support information

### Documentation Quality
- **Complete API Reference**: Request/response schemas, examples, error codes
- **Integration Workflow**: Step-by-step guide for BMA partners
- **Token Management**: Clear authentication instructions
- **Pagination Support**: Detailed pagination parameter documentation

## Implementation Files

### Core Files
- `backend/GEPPPlatform/docs/swagger/bma_public.py` (347 lines)
  - `get_bma_public_swagger_spec()` - Generate filtered OpenAPI spec
  - `get_bma_public_swagger_html()` - Generate Swagger UI HTML with BMA theme

### Integration Files
- `backend/GEPPPlatform/docs/docs_handlers.py`
  - Added route handler for `/docs/bma/0a70bf9ef2fcb7c2dc6c2b046ebb052c`
  - Returns HTML or JSON based on path

- `backend/GEPPPlatform/app.py`
  - Updated line 119 to allow `/docs/bma/` routes without authentication

## Testing

### Validation Results
```
✓ OpenAPI Version: 3.0.0
✓ Title: GEPP Platform - BMA Integration API
✓ Number of paths: 5 (covering 6 endpoint operations)
✓ Number of schemas: 10
✓ All expected paths included, no extras
✓ JSON is valid and parseable
✓ HTML validation checks passed
```

### Included Schemas
- Error
- IntegrationLoginRequest
- LoginResponse
- UserInfo
- BmaAuditStatusResponse
- BmaUsageResponse
- BmaTransactionBatchResponse
- BmaTransactionListResponse
- BmaTransactionGetResponse
- BmaMaterialAudit

## Integration Workflow

```
1. Authenticate
   POST /api/auth/integration
   → Get integration token (7-day validity)

2. Submit Transactions
   POST /api/integration/bma/transaction
   → Upload batch of waste transactions

3. Monitor Status
   GET /api/integration/bma/audit_status
   → Check AI audit processing

4. Retrieve Results
   GET /api/integration/bma/transaction
   → List transactions with pagination
   GET /api/integration/bma/transaction/{version}/{house_id}
   → Get specific transaction details

5. Track Usage
   GET /api/integration/bma/usage
   → Monitor API usage statistics
```

## Maintenance

### Adding New Endpoints
To add new endpoints to BMA public documentation:

1. Update `bma_public.py`:
   - Add path to `spec["paths"]` section (line 215-221)
   - Add required schemas to `required_schemas` list (line 228-239)

2. Update this README:
   - Add endpoint to "Included Endpoints" section
   - Update endpoint count

3. Test:
   ```bash
   python3 test_swagger_spec.py
   ```

### Changing Hash
To change the hash-protected URL:

1. Update `docs_handlers.py`:
   - Change hash in route check (line 42)

2. Update `app.py`:
   - Verify `/docs/bma/` path is allowed (line 119)

3. Update this README:
   - Update all access URLs with new hash

## Security Notes

1. **Hash as Access Control**: The hash `0a70bf9ef2fcb7c2dc6c2b046ebb052c` provides security through obscurity
2. **No Internal APIs**: Only integration-specific endpoints are exposed
3. **No Sensitive Data**: Documentation contains no credentials or secrets
4. **Public Access**: Anyone with the hash can view documentation (by design)

## Support

For BMA integration partners:
- **Email**: support@gepp.com
- **Documentation**: https://docs.gepp.com/integration/bma
- **Internal Docs**: Use `/documents/api-docs` for full API reference (requires authentication)

## Related Files

- Main Swagger aggregator: `backend/GEPPPlatform/docs/swagger/aggregator.py`
- BMA integration endpoints: `backend/GEPPPlatform/services/integrations/bma/`
- Full API documentation: `/{deployment_state}/documents/api-docs`
