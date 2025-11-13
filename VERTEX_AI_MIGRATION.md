# Vertex AI Migration Guide

This guide explains how to migrate from Gemini Developer API to Google Cloud Vertex AI for the AI audit service.

## What Changed

The transaction audit service now uses **Vertex AI** instead of the Gemini Developer API. This provides:
- Better enterprise support and SLAs
- Integration with Google Cloud IAM and security
- More control over data residency and compliance
- Access to enhanced models and features

## Configuration Changes

### Old Configuration (.env)
```bash
# Old - Gemini Developer API
GEMINI_API_KEY=your_gemini_api_key_here
```

### New Configuration (.env)
```bash
# New - Vertex AI
VERTEX_AI_PROJECT_ID=your-google-cloud-project-id
VERTEX_AI_LOCATION=us-central1

# Alternative: You can also use GOOGLE_CLOUD_PROJECT
GOOGLE_CLOUD_PROJECT=your-google-cloud-project-id
```

## Setup Steps

### 1. Enable Vertex AI in Google Cloud

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select or create your project
3. Enable the Vertex AI API:
   ```bash
   gcloud services enable aiplatform.googleapis.com
   ```

### 2. Set Up Authentication

You need to configure Google Cloud authentication. Choose one of these methods:

#### Method A: Application Default Credentials (Recommended for Local Development)
```bash
gcloud auth application-default login
```

#### Method B: Service Account (Recommended for Production)
```bash
# 1. Create a service account
gcloud iam service-accounts create vertex-ai-audit \
    --display-name="Vertex AI Audit Service"

# 2. Grant necessary permissions
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="serviceAccount:vertex-ai-audit@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/aiplatform.user"

# 3. Create and download key
gcloud iam service-accounts keys create vertex-ai-key.json \
    --iam-account=vertex-ai-audit@YOUR_PROJECT_ID.iam.gserviceaccount.com

# 4. Set environment variable
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/vertex-ai-key.json"
```

#### Method C: Workload Identity (For GKE/Cloud Run)
If running on Google Cloud services, use Workload Identity to automatically authenticate.

### 3. Update Environment Variables

Update your `.env` file:
```bash
# Required
VERTEX_AI_PROJECT_ID=your-project-id
VERTEX_AI_LOCATION=us-central1  # or asia-southeast1, europe-west1, etc.

# Optional: For production, set the service account key path
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
```

### 4. Available Locations

Choose a location closest to your users for better latency:
- `us-central1` (Iowa, USA)
- `us-east4` (Virginia, USA)
- `us-west1` (Oregon, USA)
- `europe-west1` (Belgium)
- `europe-west4` (Netherlands)
- `asia-southeast1` (Singapore)
- `asia-northeast1` (Tokyo, Japan)

## Code Changes

### Service Initialization

#### Old Code
```python
from transaction_audit_service import TransactionAuditService

# Old way
service = TransactionAuditService(gemini_api_key="your-api-key")
```

#### New Code
```python
from transaction_audit_service import TransactionAuditService

# New way - reads from environment variables
service = TransactionAuditService()

# Or explicitly pass configuration
service = TransactionAuditService(
    project_id="your-project-id",
    location="us-central1"
)
```

### API Usage

The API usage remains the same. All existing method calls work without changes:
```python
# This works exactly the same
result = service.sync_ai_audit(db, organization_id=123)
```

## Testing the Migration

### 1. Test Configuration
```python
import os
from google import genai

# Test Vertex AI client initialization
try:
    client = genai.Client(
        vertexai=True,
        project=os.getenv('VERTEX_AI_PROJECT_ID'),
        location=os.getenv('VERTEX_AI_LOCATION', 'us-central1')
    )

    # Test a simple API call
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents="Hello, this is a test"
    )

    print("✓ Vertex AI configuration is working!")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"✗ Configuration error: {str(e)}")
```

### 2. Run Audit Service Test
```bash
# Test the audit service with a small batch
python -c "
from transaction_audit_service import TransactionAuditService
service = TransactionAuditService()
print('✓ Service initialized successfully')
"
```

## Troubleshooting

### Error: "Vertex AI project ID not configured"
**Solution:** Set the `VERTEX_AI_PROJECT_ID` environment variable:
```bash
export VERTEX_AI_PROJECT_ID=your-project-id
```

### Error: "Could not automatically determine credentials"
**Solution:** Set up authentication (see Step 2 above). Most commonly:
```bash
gcloud auth application-default login
```

### Error: "Permission denied" or "403 Forbidden"
**Solution:** Ensure your service account has the `roles/aiplatform.user` role:
```bash
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="serviceAccount:YOUR_SERVICE_ACCOUNT" \
    --role="roles/aiplatform.user"
```

### Error: "API [aiplatform.googleapis.com] not enabled"
**Solution:** Enable the Vertex AI API:
```bash
gcloud services enable aiplatform.googleapis.com
```

### Error: "Invalid location"
**Solution:** Check that you're using a valid Vertex AI location. See the locations list above.

## Cost Considerations

### Pricing Differences
- **Gemini API:** Pay-per-request pricing
- **Vertex AI:** Enterprise pricing with volume discounts

### Cost Optimization Tips
1. Use appropriate regions (some are cheaper)
2. Enable caching for repeated prompts (already implemented)
3. Monitor token usage via the audit history
4. Use the thinking budget parameter to control reasoning tokens

## Rollback Plan

If you need to rollback to Gemini Developer API temporarily:

1. Keep the old code commented:
```python
# Fallback to Gemini Developer API if needed
# service = TransactionAuditService(gemini_api_key=os.getenv('GEMINI_API_KEY'))
```

2. Restore the old initialization in `transaction_audit_handlers.py`

## Benefits of Vertex AI

1. **Enterprise Support:** SLAs and dedicated support
2. **Security:** IAM integration, VPC-SC, CMEK support
3. **Compliance:** Better data residency controls
4. **Monitoring:** Cloud Monitoring and Logging integration
5. **Scalability:** Better handling of high-volume requests
6. **Cost Management:** Volume discounts and budgeting tools

## Additional Resources

- [Vertex AI Documentation](https://cloud.google.com/vertex-ai/docs)
- [Gemini API on Vertex AI](https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/gemini)
- [Authentication Guide](https://cloud.google.com/docs/authentication)
- [Vertex AI Pricing](https://cloud.google.com/vertex-ai/pricing)

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review Google Cloud logs: `gcloud logging read`
3. Contact your Google Cloud support representative
