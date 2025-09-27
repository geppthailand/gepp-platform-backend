# Transaction Module - Waste Material Journey Tracking

## Conceptual Overview

The transaction module is designed to track the complete lifecycle journey of waste materials as they move through the waste management ecosystem. This refactored design treats waste transactions as a supply chain, where materials flow from sources to destinations through various processing stages.

## Core Concepts

### 1. Transaction Records (Material Journey)
**Purpose**: Track the individual journey of each material type through the waste management system.

**Key Principle**: Each `TransactionRecord` represents a single material's movement from point A to point B, capturing:
- Material type and quantity
- Source location (where it came from)
- Destination location (where it's going)
- Processing stage (collection, sorting, recycling, disposal)
- Material condition and quality
- Chain of custody

### 2. Transactions (Grouped Movement)
**Purpose**: Group multiple `TransactionRecords` that occur together in a single shipment or transfer.

**Key Principle**: A `Transaction` is a container that groups multiple material records that are:
- Sent from the same source location
- Delivered to the same destination location
- Transferred on the same date/time
- Part of the same shipment batch

### Relationship Hierarchy

```
Transaction (Shipment Batch)
    ├── TransactionRecord 1 (Plastic - 100kg)
    ├── TransactionRecord 2 (Paper - 50kg)
    ├── TransactionRecord 3 (Metal - 25kg)
    └── TransactionRecord 4 (Glass - 30kg)
```

## Data Model Design

### Transaction Flow

```
UserLocation A (Source)
       ↓
   Transaction (2024-01-15, Batch #123)
       ├── Record: Plastic bottles, 100kg, Grade A
       ├── Record: Cardboard, 50kg, Grade B
       └── Record: Aluminum cans, 25kg, Grade A
       ↓
UserLocation B (Destination)
```

### Material Journey Tracking

Each `TransactionRecord` maintains a complete audit trail:

1. **Origin**: Where the material originally came from
2. **Current Location**: Where it is now
3. **Next Destination**: Where it's going
4. **Processing History**: What has been done to it
5. **Quality Changes**: How its condition changed
6. **Value Chain**: Economic value at each stage

## Key Features

### 1. Material Traceability
- Track individual materials from source to final disposal/recycling
- Maintain chain of custody for regulatory compliance
- Support circular economy reporting

### 2. Batch Management
- Group related materials in single shipments
- Bulk operations for efficiency
- Consolidated documentation and verification

### 3. Quality Tracking
- Material condition assessment at each stage
- Contamination tracking
- Grade classification (A, B, C, etc.)

### 4. Multi-Modal Support
- EPR (Extended Producer Responsibility) transactions
- Municipal waste collection
- Commercial waste management
- Recycling operations

### 5. Verification & Audit
- Photo documentation at pickup and delivery
- Weight verification
- Quality verification
- Audit trail for compliance

## Database Tables

### Core Tables
- `transactions` - Main grouping table for batch transfers
- `transaction_records` - Individual material journey records (merged with EPR records)
- `transaction_types` - Types of transactions (collection, transfer, processing, disposal)

### Supporting Tables
- `transaction_verification` - Verification data for transactions
- `transaction_audit_history` - Complete audit trail
- `transaction_material_conditions` - Material quality/condition tracking

### Image Storage
- Images are stored in AWS S3 bucket: `prod-gepp-platform-assets`
- Image URLs are stored in JSONB fields in both `transactions.images` and `transaction_records.images`
- No separate database tables for image storage - simplified S3-only approach

## Benefits of This Design

### 1. Clarity
- Clear separation between shipment (Transaction) and individual materials (TransactionRecords)
- Easy to understand material flow through the system

### 2. Flexibility
- Can track single material or bulk shipments
- Supports various business models (B2B, B2C, Municipal)
- Adaptable to different regulatory requirements

### 3. Scalability
- Efficient queries for large-scale operations
- Optimized for reporting and analytics
- Supports distributed operations

### 4. Compliance
- Built-in audit trail for regulatory compliance
- EPR reporting capabilities
- Environmental impact tracking

### 5. Integration
- Easy integration with IoT devices (scales, scanners)
- API-friendly structure
- Compatible with existing waste management systems

## Use Cases

### Municipal Collection
```
Transaction: Daily Collection Route #123
├── Record: Household Plastic - 500kg from District A
├── Record: Household Paper - 300kg from District A
└── Record: Household Organic - 800kg from District A
    → Destination: Sorting Facility B
```

### Recycling Center Operations
```
Transaction: Recycling Batch #456
├── Record: PET Bottles - 1000kg, Grade A, cleaned
├── Record: HDPE Containers - 500kg, Grade B, sorted
└── Record: Mixed Plastics - 200kg, Grade C, contaminated
    → Destination: Plastic Processing Plant C
```

### EPR Program
```
Transaction: Brand X EPR Collection #789
├── Record: Brand X Packaging - 150kg, post-consumer
├── Record: Brand X Bottles - 250kg, post-consumer
└── Record: Brand X Containers - 100kg, post-consumer
    → Destination: Certified Recycler D
```

## Migration Strategy

### From Legacy Tables
1. Merge `transactions` and `epr_transactions` → New `transactions` table
2. Merge `transaction_records` and `epr_transaction_records` → New `transaction_records` table
3. Consolidate image tables into unified structure
4. Maintain backward compatibility through views if needed

### Data Transformation
- Map existing transaction types to new unified types
- Convert EPR-specific fields to generic material tracking fields
- Preserve all audit history and verification data

## Future Enhancements

1. **Blockchain Integration**: Immutable record keeping
2. **Real-time Tracking**: GPS and IoT integration
3. **AI Quality Assessment**: Automated material grading
4. **Carbon Footprint**: Calculate environmental impact
5. **Market Integration**: Connect with commodity markets for recycled materials