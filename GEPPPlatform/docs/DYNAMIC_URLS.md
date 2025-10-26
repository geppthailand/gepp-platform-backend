# Dynamic URL Configuration for Swagger Documentation

## Problem

When accessing Swagger UI from different deployment versions (e.g., `/v1/docs`, `/dev/docs`, `/staging/docs`), the API endpoints were showing incorrect URLs in the "Try it out" feature.

**Example Issue:**
- User accesses: `https://api.geppdata.com/v1/docs`
- Swagger shows endpoint: `POST /dev/api/integration/bma/transaction`
- **Expected**: `POST /v1/api/integration/bma/transaction`

## Solution

We implemented a **fully dynamic URL system** that automatically detects and uses the correct base path and server URL based on the current browser location.

## How It Works

### 1. Dynamic Path Detection

When Swagger UI loads, JavaScript extracts the deployment version from the current URL:

```javascript
// Current URL: https://api.geppdata.com/v1/docs/swagger
const currentPath = window.location.pathname;  // "/v1/docs/swagger"
const basePath = currentPath.replace(/\/docs.*$/, '');  // "/v1"
```

### 2. Server URL Construction

The system builds both relative and absolute server URLs:

```javascript
const protocol = window.location.protocol;  // "https:"
const host = window.location.host;           // "api.geppdata.com"
const serverUrl = protocol + '//' + host + basePath;  // "https://api.geppdata.com/v1"
```

### 3. Spec Modification

Before rendering Swagger UI, we fetch the OpenAPI spec and override the `servers` section:

```javascript
fetch(specUrl)
    .then(response => response.json())
    .then(spec => {
        spec.servers = [
            {
                url: basePath,                              // "/v1"
                description: "Current Environment (Relative)"
            },
            {
                url: serverUrl,                             // "https://api.geppdata.com/v1"
                description: "Current Environment (Absolute)"
            }
        ];
        // Initialize Swagger UI with modified spec
    });
```

## URL Examples

### Scenario 1: Production v1
- **Docs URL**: `https://api.geppdata.com/v1/docs`
- **API Base**: `https://api.geppdata.com/v1`
- **Endpoint**: `POST https://api.geppdata.com/v1/api/integration/bma/transaction`

### Scenario 2: Development
- **Docs URL**: `https://api.geppdata.com/dev/docs`
- **API Base**: `https://api.geppdata.com/dev`
- **Endpoint**: `POST https://api.geppdata.com/dev/api/integration/bma/transaction`

### Scenario 3: Local Development
- **Docs URL**: `http://localhost:3000/dev/docs`
- **API Base**: `http://localhost:3000/dev`
- **Endpoint**: `POST http://localhost:3000/dev/api/integration/bma/transaction`

### Scenario 4: Custom Version
- **Docs URL**: `https://api.geppdata.com/my-feature-branch/docs`
- **API Base**: `https://api.geppdata.com/my-feature-branch`
- **Endpoint**: `POST https://api.geppdata.com/my-feature-branch/api/integration/bma/transaction`

## Server Selection in Swagger UI

Swagger UI provides a dropdown to select between different servers:

1. **Current Environment (Relative)** - Uses relative path (recommended)
   - Path: `/v1`
   - Best for: Browser-based testing
   - Advantage: Works across all domains

2. **Current Environment (Absolute)** - Uses full URL
   - Path: `https://api.geppdata.com/v1`
   - Best for: Copy-paste cURL commands
   - Advantage: Full URL in generated code

## Code Flow

```
User visits: https://api.geppdata.com/v1/docs/swagger
                          ↓
              JavaScript extracts: /v1
                          ↓
        Fetches: https://api.geppdata.com/v1/docs/openapi.json
                          ↓
              Modifies spec.servers array
                          ↓
           Initializes Swagger UI with modified spec
                          ↓
      All endpoints show correct URLs with /v1 prefix
```

## Benefits

✅ **Automatic Detection**: No manual configuration needed
✅ **Version Agnostic**: Works with any deployment version
✅ **Environment Agnostic**: Works in dev, staging, prod, and custom versions
✅ **Domain Agnostic**: Works on any domain (production, localhost, etc.)
✅ **User-Friendly**: Correct URLs shown immediately
✅ **Copy-Paste Ready**: Generated cURL commands have correct URLs

## Fallback Mechanism

If the dynamic spec fetch fails, the system falls back to standard URL-based loading:

```javascript
.catch(error => {
    console.error('Error loading OpenAPI spec:', error);
    // Fallback to URL-based loading
    const ui = SwaggerUIBundle({
        url: specUrl,  // Still uses dynamic URL
        // ... other config
    });
});
```

## Testing

### Test Different Versions

1. Visit: `https://api.geppdata.com/v1/docs`
   - ✅ Should show `/v1/api/*` endpoints

2. Visit: `https://api.geppdata.com/dev/docs`
   - ✅ Should show `/dev/api/*` endpoints

3. Visit: `https://api.geppdata.com/staging/docs`
   - ✅ Should show `/staging/api/*` endpoints

### Test "Try It Out"

1. Click "Try it out" on any endpoint
2. Fill in parameters
3. Click "Execute"
4. Check the "Curl" section shows the correct URL
5. Check the "Request URL" shows the correct full path

### Expected Results

- ✅ Request URL matches the docs URL version
- ✅ cURL command has correct domain and version
- ✅ Response comes from correct environment
- ✅ No CORS errors
- ✅ No 403/404 errors

## Configuration Files

### Modified Files

1. **[base.py](swagger/base.py)** - Default servers configuration
   - Provides fallback servers if dynamic detection fails

2. **[aggregator.py](swagger/aggregator.py)** - Dynamic URL injection
   - Fetches spec and modifies servers array
   - Implements fallback mechanism

3. **[docs_handlers.py](docs_handlers.py)** - Relative URL links
   - Index page uses relative URLs for portability

## Troubleshooting

### Issue: Wrong URL in Swagger
**Check**: Open browser console, look for fetch errors
**Fix**: Ensure `/docs/openapi.json` endpoint is accessible

### Issue: 403 Error on API Calls
**Check**: Verify Authorization header is set
**Fix**: Click "Authorize" button and enter JWT token

### Issue: Server dropdown shows wrong URLs
**Check**: Verify the `basePath` extraction in console
**Fix**: Check regex in `currentPath.replace(/\/docs.*$/, '')`

### Issue: CORS errors
**Check**: Ensure API server allows requests from docs domain
**Fix**: Update CORS configuration on API server

## Future Enhancements

- [ ] Add more server options (test, demo environments)
- [ ] Persist selected server in localStorage
- [ ] Auto-detect API version from deployment
- [ ] Add server health indicators
- [ ] Support custom domain mapping

## Summary

The dynamic URL system ensures that Swagger UI always shows the correct API endpoints regardless of which deployment version the documentation is accessed from. This is achieved through client-side JavaScript that detects the current URL and dynamically modifies the OpenAPI specification before rendering.

**Key Point**: No server-side changes needed - all URL detection and modification happens in the browser!
