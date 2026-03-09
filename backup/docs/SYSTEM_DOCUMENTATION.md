# GEPP Platform - System Documentation

## Overview

GEPP (Green Environment & Plastic Platform) is a comprehensive waste management and sustainability platform designed for organizations to track, manage, and report on waste transactions. The platform supports multi-tenant organizations with features for waste tracking, AI-powered auditing, GRI sustainability reporting, and mobile data collection.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              GEPP Platform                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────────┐         ┌──────────────────────────────────────┐ │
│  │   Frontend (React)   │ ◄─────► │        Backend (Python/Lambda)       │ │
│  │   gepp-business-v2   │  REST   │          GEPPPlatform                │ │
│  └──────────────────────┘   API   └──────────────────────────────────────┘ │
│           │                                        │                        │
│           │                                        │                        │
│           ▼                                        ▼                        │
│  ┌──────────────────────┐         ┌──────────────────────────────────────┐ │
│  │   Mobile Input (QR)  │         │       PostgreSQL Database            │ │
│  │   Public Access      │         │       (AWS RDS)                      │ │
│  └──────────────────────┘         └──────────────────────────────────────┘ │
│                                                    │                        │
│                                                    ▼                        │
│                                   ┌──────────────────────────────────────┐ │
│                                   │          AWS Services                │ │
│                                   │   S3 (files) | Lambda | API Gateway  │ │
│                                   └──────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Technology Stack

### Backend
| Component | Technology |
|-----------|------------|
| Runtime | Python 3.x |
| Framework | AWS Lambda (Serverless) |
| Database ORM | SQLAlchemy |
| Database | PostgreSQL (with pgvector) |
| Authentication | JWT (JSON Web Tokens) |
| File Storage | AWS S3 |
| API Gateway | AWS API Gateway |

### Frontend
| Component | Technology |
|-----------|------------|
| Framework | React 18+ with TypeScript |
| Build Tool | Vite |
| State Management | React Query (TanStack Query) |
| UI Library | Ant Design |
| Routing | React Router v6 |
| Internationalization | i18next |
| Styling | CSS-in-JS / CSS Modules |

---

## Backend Structure

### Directory Layout
```
backend/
└── GEPPPlatform/
    ├── app.py                    # Main Lambda handler & routing
    ├── database.py               # Database connection & session management
    ├── exceptions.py             # Custom API exceptions
    ├── crons.py                  # Scheduled tasks
    │
    ├── models/                   # SQLAlchemy ORM models
    │   ├── base.py               # Base model class
    │   ├── audit_rules.py        # Audit rules configuration
    │   ├── cores/                # Core domain models
    │   │   ├── locations.py      # Geographic locations
    │   │   ├── permissions.py    # RBAC permissions
    │   │   ├── roles.py          # User roles
    │   │   ├── references.py     # Reference/lookup tables
    │   │   └── translations.py   # Multi-language support
    │   ├── users/                # User-related models
    │   ├── subscriptions/        # Organization subscriptions
    │   ├── epr/                  # EPR compliance models
    │   ├── epr_payments/         # Payment transactions
    │   ├── gri/                  # GRI reporting models
    │   ├── rewards/              # Rewards/points system
    │   ├── km/                   # Knowledge management
    │   ├── chats/                # Chat/messaging
    │   └── logs/                 # Audit & platform logs
    │
    ├── services/                 # Business logic & API handlers
    │   ├── auth/                 # Authentication service
    │   │   ├── auth_handlers.py
    │   │   ├── auth_models.py
    │   │   └── dto/              # Data transfer objects
    │   ├── cores/
    │   │   ├── users/            # User management
    │   │   │   ├── user_handlers.py
    │   │   │   ├── user_service.py
    │   │   │   ├── user_permissions.py
    │   │   │   └── input_channel_service.py  # QR code input
    │   │   ├── organizations/    # Organization management
    │   │   ├── materials/        # Materials catalog
    │   │   ├── transactions/     # Waste transactions
    │   │   ├── transaction_audit/# AI audit system
    │   │   ├── audit_rules/      # Audit rules management
    │   │   ├── gri/              # GRI reporting
    │   │   ├── reports/          # Report generation
    │   │   └── iot_devices/      # IoT device management
    │   ├── integrations/
    │   │   └── bma/              # BMA (Bangkok) integration
    │   └── debug/                # Debug endpoints
    │
    ├── libs/
    │   └── authGuard.py          # Authorization utilities
    │
    └── docs/
        ├── docs_handlers.py      # API documentation
        └── swagger/              # Swagger/OpenAPI specs
```

### API Endpoints

| Endpoint | Description | Auth Required |
|----------|-------------|---------------|
| `/api/auth/*` | Authentication (login, register, token) | No |
| `/api/users/*` | User management | Yes |
| `/api/organizations/*` | Organization management | Yes |
| `/api/locations/*` | Location management | Yes |
| `/api/materials/*` | Materials catalog | Yes* |
| `/api/transactions/*` | Waste transactions CRUD | Yes |
| `/api/transaction_audit/*` | Transaction AI audit | Yes |
| `/api/audit/*` | Audit rules management | Yes |
| `/api/audit/manual/*` | Manual audit operations | Yes |
| `/api/gri/*` | GRI reporting | Yes |
| `/api/reports/*` | Report generation | Yes |
| `/api/iot-devices/*` | IoT device management | Yes (Device Token) |
| `/api/input-channel/{hash}` | QR mobile input | No (Public) |
| `/api/integration/bma/*` | BMA integration | Yes |
| `/api/debug/*` | Debug endpoints | Yes |
| `/health` | Health check | No |

*Materials endpoint supports both JWT auth and channel-based auth for mobile input

---

## Frontend Structure

### Directory Layout
```
frontend/gepp-business-v2/
├── src/
│   ├── App.tsx                   # Main app with routing
│   ├── main.tsx                  # Entry point
│   ├── vite-env.d.ts
│   │
│   ├── pages/                    # Route pages
│   │   ├── Login.tsx
│   │   ├── Register.tsx
│   │   ├── Dashboard.tsx
│   │   ├── WasteTransactions/    # Main transactions page
│   │   │   ├── index.tsx
│   │   │   ├── ListAudit.tsx
│   │   │   ├── AuditRules.tsx
│   │   │   ├── ManualAuditModal.tsx
│   │   │   ├── TransactionDetailModal.tsx
│   │   │   ├── TraceabilityModal.tsx
│   │   │   ├── MaterialSelectionModal.tsx
│   │   │   └── LogisticsBoard.tsx
│   │   ├── MobileInput/          # QR code mobile input
│   │   │   └── index.tsx
│   │   ├── GRI/                  # GRI reporting pages
│   │   │   ├── GRI306_1.tsx
│   │   │   ├── GRI306_2.tsx
│   │   │   ├── GRI306_3.tsx
│   │   │   └── GRIReports.tsx
│   │   ├── Locations.tsx
│   │   ├── Users.tsx
│   │   ├── Reports.tsx
│   │   ├── Traceability.tsx
│   │   ├── CostManagement.tsx
│   │   ├── Rewards.tsx
│   │   └── Profile.tsx
│   │
│   ├── components/               # Reusable components
│   │   ├── ProtectedRoute.tsx
│   │   ├── G360FloatingButton.tsx
│   │   └── WasteTransaction/     # Transaction-related components
│   │
│   ├── services/                 # API services
│   │   └── api/
│   │       ├── TransactionApiService.ts
│   │       └── ...
│   │
│   ├── hooks/                    # Custom React hooks
│   │   └── useTransactionData.ts
│   │
│   ├── contexts/                 # React contexts
│   │   └── AuthContextProvider.tsx
│   │
│   ├── layouts/                  # Layout components
│   │   └── TopNavLayout.tsx
│   │
│   ├── themes/                   # Theme configuration
│   ├── constants/                # App constants
│   ├── i18n/                     # Internationalization
│   └── context/
│       └── LanguageContext.tsx
│
├── public/
├── package.json
├── vite.config.ts
└── tsconfig.json
```

### Route Map

| Route | Page | Access | Description |
|-------|------|--------|-------------|
| `/login` | Login | Public | User authentication |
| `/register` | Register | Public | User registration |
| `/input/:hash` | MobileInput | Public | QR code mobile input |
| `/dashboard` | Dashboard | Protected | Main dashboard |
| `/waste-transactions` | WasteTransactions | Protected | Transaction management |
| `/reports` | Reports | Protected | Report generation |
| `/traceability` | Traceability | Protected | Waste traceability |
| `/cost-management` | CostManagement | Protected | Cost tracking |
| `/gri-306` | GRI306 | Protected | GRI 306 reporting |
| `/gri` | GRI | Protected | GRI reporting hub |
| `/locations` | Locations | Protected | Location management |
| `/users` | Users | Protected | User management |
| `/rewards` | Rewards | Protected | Rewards system |
| `/profile` | Profile | Protected | User profile |

---

## Core Workflows

### 1. QR Code Mobile Input Flow

This flow allows external users (members/employees) to submit waste data via QR code without requiring full authentication.

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  QR Code    │────►│ Mobile Web  │────►│ Validate    │────►│  Submit     │
│  Scan       │     │ /input/:hash│     │ Channel +   │     │ Transaction │
│             │     │             │     │ Sub-user    │     │             │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │ Load        │
                    │ Materials & │
                    │ Preferences │
                    └─────────────┘
```

**Steps:**
1. Organization admin generates QR code with unique hash
2. Member scans QR code, opens `/input/:hash` page
3. Frontend calls `/api/input-channel/{hash}?subuser={name}`
4. Backend validates hash and subuser, returns channel data
5. User selects materials and enters weights
6. Frontend submits to `/api/input-channel/{hash}/submit`
7. Backend creates Transaction + TransactionRecords

**Key Files:**
- Backend: `input_channel_service.py`
- Frontend: `MobileInput/index.tsx`

---

### 2. Transaction Management Flow

Full CRUD operations for waste transactions with line items (records).

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Create     │────►│ Add Line    │────►│ Submit      │────►│ AI Audit    │
│ Transaction │     │ Items       │     │ Transaction │     │ Processing  │
│             │     │ (Records)   │     │             │     │             │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                                                   │
                    ┌─────────────────────────────────────────────┘
                    ▼
             ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
             │ Manual      │────►│ Approve/    │────►│ Generate    │
             │ Review      │     │ Reject      │     │ Reports     │
             │ (if needed) │     │             │     │             │
             └─────────────┘     └─────────────┘     └─────────────┘
```

**Transaction Statuses:**
| Status | Description |
|--------|-------------|
| `pending` | Newly created, awaiting processing |
| `waiting_ai` | Submitted for AI audit |
| `in_review` | Flagged for manual review |
| `approved` | Passed audit, finalized |
| `rejected` | Failed audit, requires correction |

**Key Files:**
- Backend: `transaction_service.py`, `transaction_handlers.py`
- Frontend: `WasteTransactions/index.tsx`, `useTransactionData.ts`

---

### 3. AI Audit Flow

Automated validation of transactions based on configurable rules.

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ Transaction │────►│ Load Audit  │────►│ Execute     │────►│ Generate    │
│ Submitted   │     │ Rules       │     │ Rule Checks │     │ AI Notes    │
│             │     │             │     │             │     │             │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                                                   │
                    ┌─────────────────────────────────────────────┘
                    ▼
             ┌─────────────┐
             │ Update      │
             │ Status      │
             │ (pass/fail) │
             └─────────────┘
```

**Audit Rule Types:**
- Weight anomaly detection
- Material compatibility checks
- Price validation
- Location verification
- Duplicate detection

**Key Files:**
- Backend: `transaction_audit_service.py`, `audit_rules_service.py`
- Frontend: `ListAudit.tsx`, `AuditRules.tsx`

---

### 4. User & Organization Management

Multi-tenant organization structure with role-based access control.

```
┌───────────────────────────────────────────────────────────────────────────┐
│                              Organization                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │                          Users (Members)                             │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐            │ │
│  │  │  Admin   │  │ Manager  │  │ Auditor  │  │  Member  │            │ │
│  │  │  Role    │  │  Role    │  │  Role    │  │  Role    │            │ │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘            │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │                         Locations (Sites)                            │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐                          │ │
│  │  │  Hub A   │  │  Hub B   │  │ Branch C │                          │ │
│  │  │(collect) │  │(process) │  │  (site)  │                          │ │
│  │  └──────────┘  └──────────┘  └──────────┘                          │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │                      Input Channels (QR Codes)                       │ │
│  │  ┌──────────┐  ┌──────────┐                                        │ │
│  │  │Channel 1 │  │Channel 2 │  → Linked to specific locations         │ │
│  │  │ (hash)   │  │ (hash)   │                                        │ │
│  │  └──────────┘  └──────────┘                                        │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────────┘
```

**Key Files:**
- Backend: `user_service.py`, `organization_service.py`
- Frontend: `Users.tsx`, `Locations.tsx`

---

### 5. GRI 306 Reporting Flow

Generate sustainability reports following GRI 306 (Waste) standards.

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ Select Date │────►│ Aggregate   │────►│ Calculate   │────►│ Generate    │
│ Range       │     │ Transaction │     │ Metrics     │     │ Report      │
│             │     │ Data        │     │             │     │             │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
```

**GRI 306 Disclosures:**
- **306-1**: Waste generation and significant waste-related impacts
- **306-2**: Management of significant waste-related impacts
- **306-3**: Waste generated (by type and disposal method)

**Key Files:**
- Backend: `gri_handlers.py`
- Frontend: `GRI/GRI306_1.tsx`, `GRI306_2.tsx`, `GRI306_3.tsx`

---

## Data Models

### Core Entities

```
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│   Organization  │       │      User       │       │    Location     │
├─────────────────┤       ├─────────────────┤       ├─────────────────┤
│ id              │◄──┐   │ id              │   ┌──►│ id              │
│ name            │   │   │ email           │   │   │ name            │
│ subscription_id │   │   │ display_name    │   │   │ type            │
│ created_date    │   └───│ organization_id │   │   │ organization_id │
└─────────────────┘       │ role_id         │   │   │ address         │
                          └─────────────────┘   │   └─────────────────┘
                                                │
┌─────────────────┐       ┌─────────────────┐   │   ┌─────────────────┐
│   Transaction   │       │TransactionRecord│   │   │    Material     │
├─────────────────┤       ├─────────────────┤   │   ├─────────────────┤
│ id              │◄──────│ transaction_id  │   │   │ id              │
│ origin_id       │───────┼─────────────────┼───┘   │ name_th         │
│ destination_id  │       │ main_material_id│──────►│ name_en         │
│ status          │       │ category_id     │       │ category_id     │
│ transaction_date│       │ weight_kg       │       │ unit_name_th    │
│ created_by_id   │       │ price_per_unit  │       │ unit_name_en    │
│ ai_audit_status │       │ cleanliness     │       └─────────────────┘
│ ai_audit_note   │       │ hazardous_level │
└─────────────────┘       └─────────────────┘

┌─────────────────┐       ┌─────────────────┐
│   AuditRule     │       │  InputChannel   │
├─────────────────┤       ├─────────────────┤
│ id              │       │ id              │
│ rule_type       │       │ hash            │
│ rule_config     │       │ user_location_id│
│ is_active       │       │ organization_id │
│ created_date    │       │ is_active       │
└─────────────────┘       │ created_date    │
                          └─────────────────┘
```

---

## Authentication Flow

### JWT Token Flow

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│  Client  │────►│  Login   │────►│  Verify  │────►│  Issue   │
│          │     │  /auth   │     │ Password │     │   JWT    │
│          │◄────│          │◄────│          │◄────│          │
└──────────┘     └──────────┘     └──────────┘     └──────────┘
     │
     │ Store token
     ▼
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│  Client  │────►│  API     │────►│  Verify  │────►│  Process │
│ + Bearer │     │ Request  │     │  Token   │     │  Request │
│          │◄────│          │◄────│          │◄────│          │
└──────────┘     └──────────┘     └──────────┘     └──────────┘
```

### Token Payload Structure
```json
{
  "user_id": "uuid",
  "email": "user@example.com",
  "organization_id": "uuid",
  "role": "admin",
  "exp": 1234567890
}
```

---

## Environment Configuration

### Backend Environment Variables
```bash
# Database
DATABASE_URL=postgresql://user:pass@host:5432/dbname

# AWS
AWS_REGION=ap-southeast-1
AWS_S3_BUCKET=gepp-platform-files

# JWT
JWT_SECRET=your-secret-key
JWT_EXPIRATION=86400

# External Services
AI_AUDIT_ENDPOINT=https://ai-service.example.com
```

### Frontend Environment Variables
```bash
# API
VITE_API_URL=https://api.example.com

# Feature Flags
VITE_ENABLE_AI_AUDIT=true
VITE_ENABLE_GRI_REPORTS=true
```

---

## Deployment

### AWS Architecture
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
└─────────────────────────────────────────────────────────────────────┘
```

---

## Key Features Summary

| Feature | Description | Status |
|---------|-------------|--------|
| Multi-tenant Organizations | Support multiple organizations with isolated data | Active |
| Role-based Access Control | Admin, Manager, Auditor, Member roles | Active |
| QR Code Mobile Input | Public access for data collection | Active |
| Waste Transaction Management | Full CRUD with line items | Active |
| AI-powered Auditing | Automated transaction validation | Active |
| Manual Audit Review | Human review for flagged items | Active |
| GRI 306 Reporting | Sustainability reporting standards | Active |
| Material Catalog | Centralized materials database | Active |
| Location Management | Multi-site organization support | Active |
| IoT Device Integration | Scale and sensor data collection | Active |
| BMA Integration | Bangkok Metropolitan Admin integration | Active |
| Multi-language Support | Thai and English UI | Active |

---

## API Response Format

### Success Response
```json
{
  "success": true,
  "data": {
    // Response payload
  }
}
```

### Error Response
```json
{
  "success": false,
  "message": "Error description",
  "error_code": "ERROR_CODE",
  "errors": []  // Optional validation errors
}
```

### Paginated Response
```json
{
  "success": true,
  "data": {
    "items": [],
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total": 100,
      "pages": 5,
      "has_next": true,
      "has_prev": false
    }
  }
}
```

---

## Contact & Support

For technical questions or support, please contact the development team.

---

*Document Version: 1.0*
*Last Updated: January 2026*
