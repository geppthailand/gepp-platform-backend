# GEPP AI Manager on LINE - Project Structure

## 🎯 Product Overview

**Product Name:** GEPP AI Manager on LINE
**Core Technology:** Google Gemini 2.5 Flash (Function Calling)
**Platform:** LINE Official Account + LIFF (LINE Front-end Framework)
**Target Users:** Facility Managers, Waste Officers, ESG Teams
**Business Model:** SaaS Subscription (฿890 - ฿12,000+/month)
**Cost Model:** GEPP covers AI token costs, clients pay subscription fee

---

## 📁 Complete Project Directory Structure

```
gepp-line-ai-manager/
│
├── 📂 backend/                          # Python FastAPI Backend
│   ├── 📂 app/
│   │   ├── __init__.py
│   │   ├── main.py                      # FastAPI application entry point
│   │   ├── config.py                    # Environment variables & settings
│   │   ├── dependencies.py              # Shared dependencies (DB, Auth)
│   │   │
│   │   ├── 📂 api/                      # API Route Handlers
│   │   │   ├── __init__.py
│   │   │   ├── 📂 v1/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── line_webhook.py      # LINE Messaging API webhook handler
│   │   │   │   ├── liff.py              # LIFF endpoints (user info, data fetch)
│   │   │   │   ├── subscriptions.py     # Package subscription management
│   │   │   │   ├── analytics.py         # Usage analytics & reporting
│   │   │   │   └── admin.py             # Admin dashboard endpoints
│   │   │
│   │   ├── 📂 services/                 # Business Logic Layer
│   │   │   ├── __init__.py
│   │   │   ├── line_service.py          # LINE API integration (send messages, Flex)
│   │   │   ├── gemini_service.py        # 🧠 Gemini 2.5 Flash integration
│   │   │   ├── gepp_db_service.py       # Query GEPP Platform database
│   │   │   ├── report_generator.py      # Generate GRI/waste reports
│   │   │   ├── subscription_service.py  # Billing, usage tracking
│   │   │   └── cache_service.py         # Redis caching for Gemini context
│   │   │
│   │   ├── 📂 ai/                       # 🧠 AI Module (Core Intelligence)
│   │   │   ├── __init__.py
│   │   │   ├── gemini_client.py         # Google Gemini API client
│   │   │   ├── function_definitions.py  # Tool definitions for function calling
│   │   │   ├── prompt_templates.py      # System prompts & role definitions
│   │   │   ├── vision_processor.py      # Image analysis (waste identification)
│   │   │   ├── text_processor.py        # Text query processing
│   │   │   └── context_manager.py       # Manage conversation context (1M tokens)
│   │   │
│   │   ├── 📂 models/                   # Database Models (SQLAlchemy)
│   │   │   ├── __init__.py
│   │   │   ├── user.py                  # LINE user profiles
│   │   │   ├── subscription.py          # Package subscriptions
│   │   │   ├── conversation.py          # Chat history (for context)
│   │   │   ├── usage_log.py             # Token usage tracking
│   │   │   └── flex_template.py         # Reusable Flex Message templates
│   │   │
│   │   ├── 📂 schemas/                  # Pydantic Models (Request/Response)
│   │   │   ├── __init__.py
│   │   │   ├── line_webhook.py          # LINE webhook payloads
│   │   │   ├── gemini_request.py        # Gemini API requests
│   │   │   ├── flex_message.py          # Flex Message schemas
│   │   │   └── analytics.py             # Analytics response schemas
│   │   │
│   │   ├── 📂 utils/                    # Utility Functions
│   │   │   ├── __init__.py
│   │   │   ├── line_signature.py        # LINE webhook signature verification
│   │   │   ├── flex_builder.py          # Dynamic Flex Message builder
│   │   │   ├── chart_generator.py       # Generate chart images for reports
│   │   │   └── validators.py            # Input validation helpers
│   │   │
│   │   └── 📂 middleware/               # Middleware Components
│   │       ├── __init__.py
│   │       ├── auth.py                  # JWT authentication
│   │       ├── rate_limit.py            # Rate limiting per package tier
│   │       ├── logging.py               # Request/response logging
│   │       └── error_handler.py         # Global error handling
│   │
│   ├── 📂 database/
│   │   ├── __init__.py
│   │   ├── session.py                   # Database connection setup
│   │   └── migrations/                  # Alembic migrations
│   │       └── versions/
│   │
│   ├── 📂 tests/
│   │   ├── __init__.py
│   │   ├── 📂 unit/
│   │   │   ├── test_gemini_service.py
│   │   │   ├── test_function_calling.py
│   │   │   └── test_flex_builder.py
│   │   └── 📂 integration/
│   │       ├── test_line_webhook.py
│   │       └── test_liff_endpoints.py
│   │
│   ├── requirements.txt                 # Python dependencies
│   ├── Dockerfile                       # Docker container configuration
│   ├── .env.example                     # Environment variables template
│   └── README.md
│
├── 📂 frontend/                         # LIFF Frontend (Vue.js 3)
│   ├── 📂 public/
│   │   ├── index.html
│   │   └── favicon.ico
│   │
│   ├── 📂 src/
│   │   ├── main.ts                      # Vue app entry point
│   │   ├── App.vue                      # Root component
│   │   │
│   │   ├── 📂 views/                    # Page Components
│   │   │   ├── Dashboard.vue            # Main dashboard (waste summary)
│   │   │   ├── ReportDetail.vue         # Detailed GRI/waste reports
│   │   │   ├── Charts.vue               # Interactive charts page
│   │   │   ├── Profile.vue              # User subscription & settings
│   │   │   └── Alerts.vue               # Real-time waste alerts
│   │   │
│   │   ├── 📂 components/               # Reusable Components
│   │   │   ├── WasteChart.vue           # Waste data visualizations
│   │   │   ├── GRISummaryCard.vue       # GRI metric cards
│   │   │   ├── AlertNotification.vue    # Alert notifications
│   │   │   └── Loading.vue              # Loading states
│   │   │
│   │   ├── 📂 services/
│   │   │   ├── liff.ts                  # LIFF SDK integration
│   │   │   ├── api.ts                   # Axios API client
│   │   │   └── auth.ts                  # Authentication service
│   │   │
│   │   ├── 📂 stores/                   # Pinia State Management
│   │   │   ├── user.ts                  # User profile store
│   │   │   ├── waste.ts                 # Waste data store
│   │   │   └── subscription.ts          # Subscription info store
│   │   │
│   │   ├── 📂 composables/              # Vue Composables
│   │   │   ├── useWasteData.ts          # Waste data fetching logic
│   │   │   ├── useChart.ts              # Chart.js integration
│   │   │   └── useLiff.ts               # LIFF lifecycle hooks
│   │   │
│   │   ├── 📂 assets/
│   │   │   ├── styles/
│   │   │   │   └── main.css             # Tailwind CSS config
│   │   │   └── images/
│   │   │
│   │   └── 📂 utils/
│   │       ├── formatters.ts            # Data formatting helpers
│   │       └── constants.ts             # Constants (colors, limits)
│   │
│   ├── package.json
│   ├── vite.config.ts                   # Vite build configuration
│   ├── tailwind.config.js               # Tailwind CSS config
│   └── tsconfig.json
│
├── 📂 infrastructure/                   # Infrastructure as Code
│   ├── 📂 terraform/                    # Terraform configs
│   │   ├── main.tf                      # Main infrastructure
│   │   ├── cloudrun.tf                  # Google Cloud Run setup
│   │   ├── database.tf                  # PostgreSQL instance
│   │   └── storage.tf                   # Cloud Storage buckets
│   │
│   ├── 📂 kubernetes/                   # K8s manifests (if needed)
│   │   ├── deployment.yaml
│   │   └── service.yaml
│   │
│   └── 📂 scripts/
│       ├── deploy.sh                    # Deployment script
│       └── rollback.sh                  # Rollback script
│
├── 📂 docs/                             # Documentation
│   ├── API.md                           # API documentation
│   ├── ARCHITECTURE.md                  # System architecture
│   ├── GEMINI_FUNCTIONS.md              # Function calling guide
│   ├── LINE_SETUP.md                    # LINE OA setup guide
│   └── DEPLOYMENT.md                    # Deployment instructions
│
├── 📂 scripts/
│   ├── setup_db.py                      # Initial database setup
│   ├── seed_templates.py                # Seed Flex Message templates
│   └── test_gemini.py                   # Test Gemini connection
│
├── docker-compose.yml                   # Local development setup
├── .gitignore
├── README.md                            # Project overview
└── LICENSE
```

---

## 🧠 AI Module Deep Dive

### **ai/function_definitions.py** (Critical File)

This file defines the **tools** that Gemini 2.5 Flash can autonomously call via Function Calling:

```python
# Example Tool Definitions for Gemini Function Calling

FUNCTION_DEFINITIONS = [
    {
        "name": "get_waste_summary",
        "description": "Get waste transaction summary for a specific period",
        "parameters": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format"
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format"
                },
                "location_id": {
                    "type": "integer",
                    "description": "Location ID (optional)"
                }
            },
            "required": ["start_date", "end_date"]
        }
    },
    {
        "name": "get_gri_report",
        "description": "Generate GRI 306 sustainability report",
        "parameters": {
            "type": "object",
            "properties": {
                "year": {
                    "type": "integer",
                    "description": "Report year (e.g., 2026)"
                },
                "format": {
                    "type": "string",
                    "enum": ["summary", "detailed", "pdf"],
                    "description": "Report format"
                }
            },
            "required": ["year"]
        }
    },
    {
        "name": "identify_waste_from_image",
        "description": "Analyze waste image and identify material type",
        "parameters": {
            "type": "object",
            "properties": {
                "image_url": {
                    "type": "string",
                    "description": "URL of the waste image"
                }
            },
            "required": ["image_url"]
        }
    },
    {
        "name": "create_flex_chart",
        "description": "Create a Flex Message with waste data chart",
        "parameters": {
            "type": "object",
            "properties": {
                "chart_type": {
                    "type": "string",
                    "enum": ["bar", "pie", "line"],
                    "description": "Type of chart"
                },
                "data_period": {
                    "type": "string",
                    "description": "Period for data aggregation"
                }
            },
            "required": ["chart_type", "data_period"]
        }
    },
    {
        "name": "get_real_time_alerts",
        "description": "Fetch current waste-related alerts",
        "parameters": {
            "type": "object",
            "properties": {
                "severity": {
                    "type": "string",
                    "enum": ["all", "high", "medium", "low"],
                    "description": "Alert severity level"
                }
            }
        }
    }
]
```

### **ai/gemini_client.py** (Core AI Integration)

```python
"""
Google Gemini 2.5 Flash Client with Function Calling
"""

import google.generativeai as genai
from typing import Dict, List, Optional
import json

class GeminiClient:
    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            tools=FUNCTION_DEFINITIONS  # Enable function calling
        )

    async def chat(
        self,
        user_message: str,
        conversation_history: List[Dict],
        image_url: Optional[str] = None
    ) -> Dict:
        """
        Send a chat message to Gemini and handle function calling

        Args:
            user_message: User's text input
            conversation_history: Previous messages for context
            image_url: Optional image URL for vision analysis

        Returns:
            Response with text and/or function calls
        """

        # Prepare chat session
        chat = self.model.start_chat(history=conversation_history)

        # Send message (with image if provided)
        if image_url:
            response = await chat.send_message([user_message, image_url])
        else:
            response = await chat.send_message(user_message)

        # Handle function calling
        if response.candidates[0].content.parts[0].function_call:
            function_call = response.candidates[0].content.parts[0].function_call

            # Execute the requested function
            result = await self._execute_function(
                function_call.name,
                dict(function_call.args)
            )

            # Send function result back to Gemini
            final_response = await chat.send_message(
                Part.from_function_response(
                    name=function_call.name,
                    response={"result": result}
                )
            )

            return {
                "text": final_response.text,
                "function_called": function_call.name,
                "function_args": dict(function_call.args)
            }

        return {
            "text": response.text,
            "function_called": None
        }

    async def _execute_function(self, function_name: str, args: Dict) -> Dict:
        """
        Map Gemini function calls to actual backend services
        """
        function_map = {
            "get_waste_summary": self._get_waste_summary,
            "get_gri_report": self._get_gri_report,
            "identify_waste_from_image": self._identify_waste,
            "create_flex_chart": self._create_flex_chart,
            "get_real_time_alerts": self._get_alerts
        }

        handler = function_map.get(function_name)
        if handler:
            return await handler(**args)
        else:
            return {"error": f"Unknown function: {function_name}"}

    async def _get_waste_summary(self, start_date: str, end_date: str, location_id: Optional[int] = None):
        # Query GEPP database via gepp_db_service
        from app.services.gepp_db_service import query_waste_transactions
        return await query_waste_transactions(start_date, end_date, location_id)

    # ... other function implementations
```

---

## 🔗 Integration with Existing GEPP Platform

### Database Connection Strategy

The LINE AI Manager connects to the **existing GEPP Platform database** (PostgreSQL):

```python
# backend/app/services/gepp_db_service.py

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

# Connect to GEPP production database (read-only for safety)
GEPP_DB_URL = os.getenv("GEPP_DATABASE_URL")
gepp_engine = create_engine(GEPP_DB_URL, pool_pre_ping=True)
GEPPSession = sessionmaker(bind=gepp_engine)

async def query_waste_transactions(start_date: str, end_date: str, location_id: Optional[int]):
    """
    Query waste transactions from GEPP database
    Reuses existing table structure from backend/GEPPPlatform/models/transactions/
    """
    with GEPPSession() as session:
        query = session.query(Transaction).filter(
            Transaction.transaction_date.between(start_date, end_date)
        )

        if location_id:
            query = query.filter(Transaction.location_id == location_id)

        results = query.all()

        # Aggregate data
        total_weight = sum(t.total_weight for t in results)
        material_breakdown = {}

        for transaction in results:
            for record in transaction.records:
                material = record.material.name
                material_breakdown[material] = material_breakdown.get(material, 0) + record.weight

        return {
            "total_weight": total_weight,
            "transaction_count": len(results),
            "material_breakdown": material_breakdown,
            "period": f"{start_date} to {end_date}"
        }
```

### Flex Message Response Example

```python
# backend/app/utils/flex_builder.py

def build_waste_summary_flex(data: Dict) -> Dict:
    """
    Build LINE Flex Message for waste summary
    """
    return {
        "type": "bubble",
        "hero": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "📊 Waste Summary",
                    "weight": "bold",
                    "size": "xl",
                    "color": "#10b981"
                }
            ],
            "backgroundColor": "#d1fae5",
            "paddingAll": "20px"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": f"Period: {data['period']}",
                    "size": "sm",
                    "color": "#6b7280",
                    "margin": "md"
                },
                {
                    "type": "separator",
                    "margin": "lg"
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "margin": "lg",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "box",
                            "layout": "baseline",
                            "spacing": "sm",
                            "contents": [
                                {
                                    "type": "text",
                                    "text": "Total Weight:",
                                    "color": "#374151",
                                    "size": "sm",
                                    "flex": 3
                                },
                                {
                                    "type": "text",
                                    "text": f"{data['total_weight']:,.2f} kg",
                                    "wrap": True,
                                    "color": "#10b981",
                                    "size": "md",
                                    "weight": "bold",
                                    "flex": 2,
                                    "align": "end"
                                }
                            ]
                        },
                        {
                            "type": "box",
                            "layout": "baseline",
                            "spacing": "sm",
                            "contents": [
                                {
                                    "type": "text",
                                    "text": "Transactions:",
                                    "color": "#374151",
                                    "size": "sm",
                                    "flex": 3
                                },
                                {
                                    "type": "text",
                                    "text": str(data['transaction_count']),
                                    "wrap": True,
                                    "color": "#059669",
                                    "size": "md",
                                    "weight": "bold",
                                    "flex": 2,
                                    "align": "end"
                                }
                            ]
                        }
                    ]
                },
                {
                    "type": "separator",
                    "margin": "lg"
                },
                {
                    "type": "text",
                    "text": "Material Breakdown:",
                    "size": "sm",
                    "weight": "bold",
                    "margin": "lg"
                },
                # Dynamic material list
                *[
                    {
                        "type": "box",
                        "layout": "baseline",
                        "spacing": "sm",
                        "contents": [
                            {
                                "type": "text",
                                "text": material,
                                "color": "#6b7280",
                                "size": "xs",
                                "flex": 3
                            },
                            {
                                "type": "text",
                                "text": f"{weight:,.1f} kg",
                                "color": "#374151",
                                "size": "xs",
                                "flex": 2,
                                "align": "end"
                            }
                        ]
                    }
                    for material, weight in data['material_breakdown'].items()
                ]
            ]
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "action": {
                        "type": "uri",
                        "label": "View Details",
                        "uri": "https://liff.line.me/YOUR_LIFF_ID/dashboard"
                    },
                    "color": "#10b981"
                }
            ],
            "flex": 0
        }
    }
```

---

## 🚀 Deployment Architecture (Google Cloud Run)

```yaml
# infrastructure/terraform/cloudrun.tf

resource "google_cloud_run_service" "gepp_line_ai" {
  name     = "gepp-line-ai-manager"
  location = "asia-southeast1"  # Thailand region

  template {
    spec {
      containers {
        image = "gcr.io/gepp-platform/line-ai-manager:latest"

        env {
          name  = "GEMINI_API_KEY"
          value_from {
            secret_key_ref {
              name = "gemini-api-key"
              key  = "latest"
            }
          }
        }

        env {
          name  = "LINE_CHANNEL_SECRET"
          value_from {
            secret_key_ref {
              name = "line-channel-secret"
              key  = "latest"
            }
          }
        }

        env {
          name  = "GEPP_DATABASE_URL"
          value = var.gepp_database_url
        }

        resources {
          limits = {
            cpu    = "2000m"
            memory = "2Gi"
          }
        }
      }

      container_concurrency = 80
    }

    metadata {
      annotations = {
        "autoscaling.knative.dev/minScale" = "1"
        "autoscaling.knative.dev/maxScale" = "10"
      }
    }
  }

  traffic {
    percent         = 100
    latest_revision = true
  }
}
```

---

## 📊 Cost Optimization Strategies

### 1. Context Caching (75% Cost Reduction)
```python
# Use Google Gemini Context Caching for repeated system prompts
# Cache the GEPP system prompt + material catalog for 1 hour

CACHED_CONTEXT = """
You are GEPP AI Manager, an AI assistant for waste management.

Material Catalog:
- PET Plastic (Code: PET-001)
- Glass Bottles (Code: GLS-002)
- Cardboard (Code: CBD-003)
... (1000+ materials)

Current User Organization: [Organization Name]
Available Locations: [Location Tree]
"""

# This context is cached and reused across all conversations
# Reduces input tokens from ~5000 to ~200 per query
```

### 2. Batch Processing for Reports
```python
# Generate daily summaries in batch at 6 AM (off-peak)
# Use Gemini Batch API for 50% discount

async def batch_generate_daily_summaries():
    users = await get_all_active_subscriptions()

    batch_requests = [
        {
            "user_id": user.id,
            "prompt": f"Generate daily waste summary for {user.organization_name}"
        }
        for user in users
    ]

    # Send as batch (cheaper + non-urgent)
    results = await gemini_client.batch_generate(batch_requests)

    # Send results via LINE Notify (no interactive chat cost)
    for result in results:
        await line_service.push_message(result.user_id, result.summary)
```

### 3. Smart Rate Limiting
```python
# Prevent abuse while staying within package limits

PACKAGE_LIMITS = {
    "starter": {"daily": 3, "monthly": 100},
    "pro": {"daily": 70, "monthly": 2000},
    "enterprise": {"daily": 9999, "monthly": 999999}
}

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    user = request.state.user
    usage = await get_monthly_usage(user.id)

    package = user.subscription_package
    limit = PACKAGE_LIMITS[package]["monthly"]

    if usage >= limit:
        return JSONResponse(
            status_code=429,
            content={"error": "Monthly quota exceeded. Please upgrade your package."}
        )

    response = await call_next(request)
    return response
```

---

## 🎯 Key Differentiators

| Feature | Traditional Chatbot | GEPP AI Manager |
|---------|---------------------|-----------------|
| **Response Time** | 2-5 seconds | < 0.5 seconds (Gemini 2.5 Flash) |
| **Intelligence** | Rule-based | AI Function Calling (autonomous DB queries) |
| **Vision Capability** | No | Yes (snap waste photo → instant ID) |
| **Context Memory** | 2k tokens (~3 messages) | 1M tokens (entire month of conversations) |
| **Cost** | $0.50-$2 per request | $0.0005 per request (text) |
| **Integration** | Custom API per query | Single Gemini model handles all |
| **Scalability** | Linear cost increase | Cached context = fixed cost |

---

## 📚 Technology Choices Rationale

### Why Google Gemini 2.5 Flash?
1. **Speed:** < 0.5s latency (critical for LINE chat UX)
2. **Cost:** $0.10/M tokens (5-10x cheaper than GPT-4 Turbo)
3. **Multimodal:** Native image + text processing (no separate vision model)
4. **Context:** 1M token window (can analyze entire monthly reports)
5. **Function Calling:** Native tool use (no prompt engineering needed)

### Why FastAPI?
1. **Async:** Handles concurrent LINE webhooks efficiently
2. **Fast:** Python's fastest web framework (Node.js-level performance)
3. **Type Safety:** Pydantic validation (catches errors at dev time)
4. **OpenAPI:** Auto-generated API docs (easier for team collaboration)

### Why Vue.js for LIFF?
1. **Lightweight:** Smaller bundle size than React (faster load on mobile)
2. **Simple:** Easier learning curve for Thai developers
3. **Reactive:** Perfect for real-time data updates (waste alerts)
4. **LINE Integration:** Official LIFF examples use Vue.js

### Why Google Cloud Run?
1. **Serverless:** Auto-scaling (0 to 1000 requests/sec)
2. **Cost:** Pay only for requests (no idle costs)
3. **Fast Deploy:** Container-based (< 2 min deploy time)
4. **Gemini Integration:** Same cloud = lower latency

---

## 🔐 Security Considerations

```python
# backend/app/middleware/auth.py

from linebot.v3.webhooks import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError

async def verify_line_signature(request: Request):
    """
    Verify LINE webhook signature to prevent spoofing
    """
    signature = request.headers.get("X-Line-Signature")
    body = await request.body()

    try:
        parser = WebhookParser(settings.LINE_CHANNEL_SECRET)
        parser.parse(body.decode("utf-8"), signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    return True

# Apply to LINE webhook endpoint
@app.post("/api/v1/line-webhook")
async def line_webhook(
    request: Request,
    _: bool = Depends(verify_line_signature)
):
    # Process webhook...
    pass
```

---

## 📈 Success Metrics (KPIs)

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Response Time** | < 0.5s | Gemini API latency |
| **Accuracy** | > 95% | Function calling success rate |
| **User Satisfaction** | > 4.5/5 | In-chat rating prompt |
| **Cost per User** | < ฿50/month | AI + infra costs |
| **Profit Margin** | > 85% | (Revenue - Cost) / Revenue |
| **Monthly Active Users** | > 80% | Users with ≥1 message/month |
| **Conversion Rate** | > 30% | Trial → Paid conversion |

---

## 🚦 Development Roadmap

### Phase 1: MVP (Month 1-2)
- [ ] LINE Official Account setup
- [ ] Basic text chat with Gemini 2.5 Flash
- [ ] Function calling for waste summary
- [ ] Simple Flex Message responses
- [ ] Starter package implementation

### Phase 2: Vision & Reports (Month 3-4)
- [ ] Image upload → waste identification
- [ ] GRI report generation
- [ ] LIFF dashboard (basic)
- [ ] Pro package features
- [ ] Context caching optimization

### Phase 3: Enterprise Features (Month 5-6)
- [ ] Video analysis (long video processing)
- [ ] Custom LIFF dashboard (Vue.js)
- [ ] Real-time alerts via LINE Notify
- [ ] Advanced analytics
- [ ] Enterprise package launch

### Phase 4: Scale & Optimize (Month 7+)
- [ ] Multi-language support (Thai, English)
- [ ] Batch processing for cost savings
- [ ] AI model fine-tuning (optional)
- [ ] White-label solution for partners

---

## 📞 Support & Maintenance

```python
# Automated health checks

@app.get("/health")
async def health_check():
    """
    Health check for Google Cloud Run
    """
    return {
        "status": "healthy",
        "gemini_connected": await test_gemini_connection(),
        "database_connected": await test_db_connection(),
        "line_api_connected": await test_line_api()
    }

# Monitoring alerts (Cloud Monitoring)
# - Alert if response time > 1s
# - Alert if error rate > 1%
# - Alert if daily cost > ฿500
```

---

## 🎓 Training Data Requirements

For optimal performance, Gemini 2.5 Flash should be provided with:

1. **Material Catalog** (from GEPP database)
   - ~1,000 material types with codes
   - Thai + English names
   - Categories (plastic, metal, paper, etc.)

2. **Sample Conversations** (for prompt engineering)
   - "สรุปของเสียเดือนนี้" → call `get_waste_summary()`
   - "ส่งรูปขยะมา" → call `identify_waste_from_image()`
   - "ทำรายงาน GRI" → call `get_gri_report()`

3. **Business Logic Rules** (in system prompt)
   - Hazardous waste threshold: > 100 kg/month
   - Alert if waste increases > 20% month-over-month
   - Recommend recycling if diversion rate < 60%

---

**Document Version:** 1.0
**Last Updated:** February 10, 2026
**Author:** GEPP Sa-Ard Solutions Architect Team
**Contact:** [Your contact info]
