# Quick Start: Vertex AI Setup

This is a quick reference for setting up Vertex AI for the transaction audit service.

## Prerequisites

- Google Cloud account with billing enabled
- A Google Cloud project
- `gcloud` CLI installed ([Install Guide](https://cloud.google.com/sdk/docs/install))

## 5-Minute Setup

### 1. Set Project and Enable API
```bash
# Set your project
export PROJECT_ID="your-project-id"
gcloud config set project $PROJECT_ID

# Enable Vertex AI API
gcloud services enable aiplatform.googleapis.com
```

### 2. Authenticate
```bash
# For local development
gcloud auth application-default login

# Follow the browser prompts to authenticate
```

### 3. Configure Environment
```bash
# Add to your .env file
echo "VERTEX_AI_PROJECT_ID=$PROJECT_ID" >> .env
echo "VERTEX_AI_LOCATION=us-central1" >> .env
```

### 4. Test Configuration
```bash
# Run the test script
python backend/test_vertex_ai.py
```

If all tests pass, you're ready to go! ✓

## Production Setup (Additional Steps)

For production deployments, use a service account instead of user credentials:

### 1. Create Service Account
```bash
gcloud iam service-accounts create vertex-ai-audit \
    --display-name="Vertex AI Audit Service" \
    --project=$PROJECT_ID
```

### 2. Grant Permissions
```bash
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:vertex-ai-audit@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/aiplatform.user"
```

### 3. Create and Download Key
```bash
gcloud iam service-accounts keys create vertex-ai-key.json \
    --iam-account=vertex-ai-audit@$PROJECT_ID.iam.gserviceaccount.com
```

### 4. Set Key Path
```bash
# Add to .env
echo "GOOGLE_APPLICATION_CREDENTIALS=/path/to/vertex-ai-key.json" >> .env
```

## Location Selection

Choose a location based on your requirements:

| Location | Region | Best For |
|----------|--------|----------|
| `us-central1` | Iowa, USA | North America (default) |
| `us-east4` | Virginia, USA | East Coast USA |
| `asia-southeast1` | Singapore | Southeast Asia |
| `asia-northeast1` | Tokyo | Japan/Northeast Asia |
| `europe-west1` | Belgium | Europe |

Update `VERTEX_AI_LOCATION` in your `.env` file with your chosen location.

## Verification Checklist

- [ ] Google Cloud project created
- [ ] Vertex AI API enabled
- [ ] Authentication configured (gcloud login or service account)
- [ ] Environment variables set (`VERTEX_AI_PROJECT_ID`, `VERTEX_AI_LOCATION`)
- [ ] Test script passes all checks (`python backend/test_vertex_ai.py`)

## Common Issues

### "Permission denied" or "403 Forbidden"
**Fix:** Ensure Vertex AI API is enabled and you have the `aiplatform.user` role:
```bash
gcloud services enable aiplatform.googleapis.com
```

### "Could not automatically determine credentials"
**Fix:** Run authentication:
```bash
gcloud auth application-default login
```

### "API not enabled in project"
**Fix:** Enable the Vertex AI API:
```bash
gcloud services enable aiplatform.googleapis.com
```

## Cost Estimate

For reference, typical costs for the audit service:
- **Gemini 2.5 Flash:** ~$0.075 per 1M input tokens, ~$0.30 per 1M output tokens
- **With reasoning tokens:** Additional ~$0.30 per 1M reasoning tokens
- **Images:** ~$0.00025 per image

Example: Processing 1000 transactions with 2 images each:
- ~500K tokens input
- ~200K tokens output
- 2000 images
- **Estimated cost:** ~$0.60-1.00

## Next Steps

1. Read the full migration guide: [VERTEX_AI_MIGRATION.md](./VERTEX_AI_MIGRATION.md)
2. Run the test script: `python backend/test_vertex_ai.py`
3. Deploy and monitor your first audit batch
4. Set up billing alerts in Google Cloud Console

## Support

- **Documentation:** See [VERTEX_AI_MIGRATION.md](./VERTEX_AI_MIGRATION.md)
- **Google Cloud Support:** [https://cloud.google.com/support](https://cloud.google.com/support)
- **Vertex AI Docs:** [https://cloud.google.com/vertex-ai/docs](https://cloud.google.com/vertex-ai/docs)
