# GEPP Platform - Architecture Documentation

## Overview

GEPP (Green Environment & Plastic Platform) is a comprehensive waste management and ESG (Environmental, Social, Governance) platform designed for organizations to track, manage, and report on waste transactions with AI-powered insights.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                               GEPP Platform Architecture                              │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                       │
│   ┌─────────────────────┐          REST API          ┌───────────────────────────┐  │
│   │   Frontend (React)  │ ◄─────────────────────────►│    Backend (Python)       │  │
│   │   gepp-business-v2  │                            │     AWS Lambda            │  │
│   │   ┌───────────────┐ │                            │   ┌─────────────────────┐ │  │
│   │   │ Transactions  │ │                            │   │   Transaction Mgmt  │ │  │
│   │   │ Reports/GRI   │ │                            │   │   AI Audit Engine   │ │  │
│   │   │ Setup/Config  │ │                            │   │   GRI Reporting     │ │  │
│   │   │ G360 AI Chat  │ │                            │   │   ESG Analytics     │ │  │
│   │   └───────────────┘ │                            │   └─────────────────────┘ │  │
│   └─────────────────────┘                            └───────────────────────────┘  │
│            │                                                      │                  │
│            │                                                      │                  │
│            ▼                                                      ▼                  │
│   ┌─────────────────────┐                            ┌───────────────────────────┐  │
│   │   Mobile Input (QR) │                            │     AI/ML Services        │  │
│   │   Public Access     │                            │   ┌─────────────────────┐ │  │
│   └─────────────────────┘                            │   │ Google Vertex AI    │ │  │
│                                                      │   │ (Gemini Pro Vision) │ │  │
│                                                      │   └─────────────────────┘ │  │
│                                                      └───────────────────────────┘  │
│                                                                   │                  │
│                                                                   ▼                  │
│                                                      ┌───────────────────────────┐  │
│                                                      │   PostgreSQL + pgvector   │  │
│                                                      │   AWS S3 (Files)          │  │
│                                                      └───────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Technology Stack

### Frontend
| Component | Technology |
|-----------|------------|
| Framework | React 18+ with TypeScript |
| Build Tool | Vite |
| State Management | TanStack Query (React Query) |
| UI Library | Ant Design |
| Routing | React Router v7 |
| i18n | i18next (Thai/English) |
| Charts | Ant Design Plots, Chart.js |
| E2E Testing | Playwright |

### Backend
| Component | Technology |
|-----------|------------|
| Runtime | Python 3.x |
| Framework | AWS Lambda (Serverless) |
| Database | PostgreSQL with pgvector |
| ORM | SQLAlchemy |
| Authentication | JWT with token refresh |
| File Storage | AWS S3 |
| AI/ML | Google Vertex AI (Gemini) |

---

## Core Features

### 1. Transaction Management

Complete waste transaction lifecycle with CRUD operations, line items (records), and status tracking.

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Create    │────►│  Add Items  │────►│   Submit    │────►│  AI Audit   │
│ Transaction │     │  (Records)  │     │             │     │  Processing │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                                                   │
                    ┌──────────────────────────────────────────────┘
                    ▼
             ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
             │   Manual    │────►│   Approve/  │────►│  Generate   │
             │   Review    │     │   Reject    │     │   Reports   │
             └─────────────┘     └─────────────┘     └─────────────┘
```

**Transaction Statuses:**
- `pending` → Newly created
- `waiting_ai` → Submitted for AI audit
- `in_review` → Flagged for manual review
- `approved` → Passed audit
- `rejected` → Failed audit

---

### 2. AI-Powered Auditing

Automated transaction validation using Google Vertex AI with two-phase processing:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    AI Audit Pipeline (Two-Phase)                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Phase 1: Extraction                    Phase 2: Judgment               │
│  ┌─────────────────────┐               ┌─────────────────────┐         │
│  │ • Analyze images    │               │ • Apply audit rules │         │
│  │ • Extract materials │──────────────►│ • Cross-reference   │         │
│  │ • Identify weights  │               │ • Generate verdict  │         │
│  │ • Detect anomalies  │               │ • Create AI notes   │         │
│  └─────────────────────┘               └─────────────────────┘         │
│                                                   │                     │
│                                                   ▼                     │
│                                        ┌─────────────────────┐         │
│                                        │ Update Status       │         │
│                                        │ (pass/flag/fail)    │         │
│                                        └─────────────────────┘         │
└─────────────────────────────────────────────────────────────────────────┘
```

**AI Capabilities:**
- **Image Analysis**: Material identification from photos
- **Weight Anomaly Detection**: Statistical validation
- **Material Compatibility**: Cross-verification with catalog
- **Price Validation**: Market rate comparison
- **Duplicate Detection**: Historical pattern matching

**Key Files:**
- `transaction_audit_service.py` (2,400+ lines)
- `prompt_base.json`, `image_extraction_rules.json`

---

### 3. GRI Sustainability Reporting

GRI 306 (Waste) standards compliance with automated data aggregation:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      GRI 306 Reporting Suite                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐        │
│  │   GRI 306-1     │  │   GRI 306-2     │  │   GRI 306-3     │        │
│  │ Waste Generated │  │ Management of   │  │ Waste by Type   │        │
│  │ & Impacts       │  │ Waste Impacts   │  │ & Disposal      │        │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘        │
│         │                     │                     │                   │
│         └─────────────────────┼─────────────────────┘                  │
│                               ▼                                         │
│                    ┌─────────────────────┐                             │
│                    │   PDF Export        │                             │
│                    │   Annual Reports    │                             │
│                    └─────────────────────┘                             │
└─────────────────────────────────────────────────────────────────────────┘
```

**Features:**
- Automated aggregation from transaction data
- Hazardous/Non-hazardous classification
- Diversion vs Disposal tracking
- PDF report generation
- Year-over-year comparison

---

### 4. AI-Driven ESG Consulting (G360)

Interactive AI assistant for sustainability guidance:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        G360 AI Consulting                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   ┌─────────────────┐         ┌─────────────────────────────────────┐  │
│   │ Floating Button │────────►│      G360 Chat Interface            │  │
│   │ (All Pages)     │         │  ┌────────────────────────────────┐ │  │
│   └─────────────────┘         │  │ • ESG Score Analysis          │ │  │
│                               │  │ • Improvement Recommendations │ │  │
│                               │  │ • Compliance Guidance         │ │  │
│                               │  │ • Best Practices Suggestions  │ │  │
│                               │  │ • Carbon Footprint Insights   │ │  │
│                               │  └────────────────────────────────┘ │  │
│                               └─────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

**Capabilities:**
- Contextual ESG recommendations
- Waste reduction strategies
- Regulatory compliance tips
- Sustainability benchmarking
- Carbon emission calculations

---

### 5. Setup & Configuration

Multi-tenant organization management with hierarchical structure:

```
┌───────────────────────────────────────────────────────────────────────────┐
│                              Organization                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │                          Users (RBAC)                                │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐            │ │
│  │  │  Admin   │  │ Manager  │  │ Auditor  │  │  Viewer  │            │ │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘            │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │                    Location Hierarchy (Tree)                         │ │
│  │           ┌────────────┐                                            │ │
│  │           │ Head Office│                                            │ │
│  │           └─────┬──────┘                                            │ │
│  │        ┌────────┼────────┐                                          │ │
│  │   ┌────┴────┐   │   ┌────┴────┐                                    │ │
│  │   │  Hub A  │   │   │  Hub B  │                                    │ │
│  │   └────┬────┘   │   └────┬────┘                                    │ │
│  │   ┌────┴────┐   │   ┌────┴────┐                                    │ │
│  │   │Branch 1 │   │   │Branch 2 │                                    │ │
│  │   └─────────┘   │   └─────────┘                                    │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │                      Audit Rules                                     │ │
│  │  • Weight thresholds  • Price limits  • Material compatibility      │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## API Structure

### Endpoint Categories

| Category | Endpoints | Description |
|----------|-----------|-------------|
| **Auth** | `/api/auth/*` | Login, register, token refresh |
| **Transactions** | `/api/transactions/*` | CRUD operations |
| **Audit** | `/api/transaction_audit/*` | AI audit processing |
| **Audit Rules** | `/api/audit/*` | Rule configuration |
| **GRI** | `/api/gri/*` | Sustainability reporting |
| **Reports** | `/api/reports/*` | Report generation |
| **Locations** | `/api/locations/*` | Site management |
| **Users** | `/api/users/*` | User management |
| **Materials** | `/api/materials/*` | Material catalog |
| **Mobile** | `/api/input-channel/*` | QR code input |

---

## Data Flow

### Transaction to Report Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Mobile    │     │  Create     │     │  AI Audit   │     │  Approved   │
│   Input     │────►│ Transaction │────►│  Process    │────►│ Transaction │
│   (QR)      │     │             │     │             │     │             │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                                                   │
    ┌──────────────────────────────────────────────────────────────┘
    ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Aggregate  │────►│  Calculate  │────►│  Generate   │
│  by Period  │     │  KPIs/GRI   │     │  Reports    │
└─────────────┘     └─────────────┘     └─────────────┘
```

---

## Deployment Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         AWS Cloud                                    │
│  ┌───────────────┐    ┌───────────────┐    ┌───────────────┐       │
│  │  CloudFront   │───►│  S3 (Static)  │    │  S3 (Files)   │       │
│  │  (CDN)        │    │  Frontend     │    │  Uploads      │       │
│  └───────────────┘    └───────────────┘    └───────────────┘       │
│         │                                                           │
│         ▼                                                           │
│  ┌───────────────┐    ┌───────────────┐    ┌───────────────┐       │
│  │  API Gateway  │───►│    Lambda     │───►│     RDS       │       │
│  │               │    │  (Backend)    │    │  PostgreSQL   │       │
│  └───────────────┘    └───────────────┘    └───────────────┘       │
│                              │                                      │
│                              ▼                                      │
│                       ┌───────────────┐                            │
│                       │ Vertex AI     │                            │
│                       │ (Gemini)      │                            │
│                       └───────────────┘                            │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Key Files Reference

### Backend
| Path | Description |
|------|-------------|
| `backend/GEPPPlatform/app.py` | Main Lambda handler & routing |
| `services/cores/transactions/` | Transaction CRUD |
| `services/cores/transaction_audit/` | AI audit engine |
| `services/cores/gri/` | GRI reporting |
| `services/cores/organizations/` | Org management |
| `services/cores/users/` | User management |
| `services/auth/` | Authentication |

### Frontend
| Path | Description |
|------|-------------|
| `src/pages/WasteTransactions/` | Transaction UI |
| `src/pages/GRI/` | GRI reporting pages |
| `src/pages/Locations.tsx` | Location setup |
| `src/components/G360FloatingButton.tsx` | AI assistant |
| `src/services/api/` | API services |
| `src/contexts/AuthContextProvider.tsx` | Auth state |

---

*Document Version: 1.0 | Last Updated: January 2026*
