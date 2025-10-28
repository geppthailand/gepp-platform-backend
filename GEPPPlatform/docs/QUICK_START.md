# API Documentation - Quick Start Guide

## 🚀 Accessing the Documentation

### For Developers

Visit the documentation portal at:

```
https://api.gepp.com/{environment}/docs
```

Replace `{environment}` with:
- `dev` - Development
- `staging` - Staging
- `prod` - Production

### Available Formats

1. **🌐 Landing Page**: `/{env}/docs`
   - Overview and links to all documentation formats

2. **📚 Swagger UI**: `/{env}/docs/swagger`
   - Interactive API explorer
   - Test endpoints directly
   - Best for: Development and testing

3. **📖 ReDoc**: `/{env}/docs/redoc`
   - Clean, professional documentation
   - Better for reading and understanding
   - Best for: API reference and onboarding

4. **📄 JSON Spec**: `/{env}/docs/openapi.json`
   - Raw OpenAPI specification
   - Best for: Import into tools (Postman, etc.)

5. **📝 YAML Spec**: `/{env}/docs/openapi.yaml`
   - Human-readable specification
   - Best for: Version control and review

## 🔑 Quick Authentication

### Step 1: Get Your Token

```bash
curl -X POST "https://api.gepp.com/dev/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "your-email@example.com",
    "password": "your-password"
  }'
```

### Step 2: Use Token in Requests

#### cURL
```bash
curl -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  "https://api.gepp.com/dev/api/transactions"
```

#### Swagger UI
1. Click the "Authorize" button (🔓)
2. Enter: `Bearer YOUR_TOKEN_HERE`
3. Click "Authorize"
4. Now you can test all endpoints!

## 📱 Using Swagger UI

### Try It Out Feature

1. Navigate to `/{env}/docs/swagger`
2. Click "Authorize" and enter your JWT token
3. Find the endpoint you want to test
4. Click "Try it out"
5. Fill in parameters
6. Click "Execute"
7. See the response!

### Features
- ✅ Interactive request builder
- ✅ Auto-generated code samples
- ✅ Live request/response
- ✅ Schema validation
- ✅ Examples for all endpoints

## 🎯 Common Use Cases

### 1. BMA Integration

**Endpoint**: `POST /api/integration/bma/transaction`

**Quick Test**:
```json
{
  "batch": {
    "v2025-Q1": {
      "2170": {
        "00000000001": {
          "timestamp": "2025-10-23T08:30:00+07:00",
          "material": {
            "general": {
              "image_url": "https://example.com/image.jpg"
            }
          }
        }
      }
    }
  }
}
```

**Note:** Use 11-digit house IDs (e.g., '00000000001', '00000000002') for consistency.

### 2. List Transactions

**Endpoint**: `GET /api/transactions`

**Query Parameters**:
- `page=1`
- `limit=20`
- `status=pending`

### 3. Create Transaction

**Endpoint**: `POST /api/transactions`

See full schema in Swagger UI!

## 🛠️ Import into Tools

### Postman

1. Open Postman
2. Click "Import"
3. Enter URL: `https://api.gepp.com/dev/docs/openapi.json`
4. Click "Import"
5. All endpoints are now in Postman!

### Insomnia

1. Open Insomnia
2. Click "Create" → "Import from URL"
3. Enter: `https://api.gepp.com/dev/docs/openapi.json`
4. Click "Fetch and Import"

### VS Code (REST Client)

1. Install "REST Client" extension
2. Create `.http` file
3. Use OpenAPI spec as reference

## 📚 API Modules

| Module | Description | Base Path |
|--------|-------------|-----------|
| **Auth** | Login, register, tokens | `/api/auth/*` |
| **Organizations** | Manage organizations | `/api/organizations/*` |
| **Users** | User management | `/api/users/*` |
| **Materials** | Material catalog | `/api/materials/*` |
| **Transactions** | Transaction tracking | `/api/transactions/*` |
| **Audit** | Compliance & auditing | `/api/audit/*` |
| **Reports** | Analytics | `/api/reports/*` |
| **Integration** | External systems | `/api/integration/*` |
| **BMA** | BMA integration | `/api/integration/bma/*` |

## ⚡ Tips & Tricks

### Swagger UI

- **Persist Auth**: Your token stays active across page refreshes
- **Filter**: Use the filter box to search endpoints
- **Expand All**: Click "Expand All" to see all endpoints at once
- **Download Spec**: Download the spec for offline use

### ReDoc

- **Search**: Use Cmd/Ctrl + F to search
- **Scroll Sync**: Left menu syncs with scrolling
- **Deep Links**: Share direct links to specific endpoints
- **Print**: Print-friendly documentation

### General

- **Test in Dev**: Always test in `dev` environment first
- **Check Examples**: Every endpoint has request/response examples
- **Read Descriptions**: Detailed descriptions explain business logic
- **Error Codes**: All error responses are documented

## 🆘 Troubleshooting

### "Unauthorized" Error
- Check token is valid
- Ensure "Bearer " prefix in Authorization header
- Token may have expired - get a new one

### "Route Not Found"
- Check deployment environment (dev/staging/prod)
- Verify path matches documentation
- Ensure HTTP method is correct

### Swagger UI Not Loading
- Check internet connection (loads CDN resources)
- Clear browser cache
- Try different browser
- Check browser console for errors

## 📞 Getting Help

1. **Documentation**: Start with this guide and Swagger UI
2. **Examples**: Check the "Examples" tab in Swagger UI
3. **Team**: Contact GEPP Platform development team
4. **Support**: support@gepp.com

## 🎓 Next Steps

1. ✅ Browse the API in Swagger UI
2. ✅ Get authentication token
3. ✅ Try a simple GET request
4. ✅ Test with your use case
5. ✅ Import into your preferred tool
6. ✅ Start building!

---

**Happy Coding! 🚀**
