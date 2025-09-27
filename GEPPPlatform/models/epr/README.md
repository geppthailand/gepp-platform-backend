# EPR Module - Extended Producer Responsibility

## Overview
The EPR (Extended Producer Responsibility) module manages comprehensive compliance frameworks for organizations responsible for the lifecycle management of their products and packaging. It supports regulatory requirements, target tracking, project management, and multi-stakeholder collaboration in extended producer responsibility programs.

## Core Concepts

### Extended Producer Responsibility
EPR is a policy approach where producers take responsibility for the environmental impacts of their products throughout the product lifecycle, including:
- **Product Design**: Eco-design and recyclability considerations
- **Collection Systems**: Take-back and collection infrastructure
- **Processing & Recycling**: Ensuring proper end-of-life treatment
- **Reporting & Compliance**: Meeting regulatory targets and reporting requirements
- **Financial Responsibility**: Covering costs of collection and processing

### EPR Organization Hierarchy
```
Main Organization (Subscription/Billing)
    ↓
EPR Organization (Compliance Entity)
    ├── EPR Projects (Product Lines/Campaigns)
    ├── Material Groups (Packaging Types)
    ├── Collection Programs (Take-back Systems)
    └── Recycling Targets (Compliance Goals)
```

## Architecture Design

### 1. Multi-Level Organization Structure
- **Main Organizations**: Core business entities with subscriptions
- **EPR Organizations**: Specialized compliance entities linked to main organizations
- **Flexibility**: One main organization can have multiple EPR entities (different regions, products, subsidiaries)

### 2. Material Group Management
Hierarchical material classification:
- **Material Groups**: Primary categories (Packaging, Electronics, Textiles)
- **Specific Materials**: Individual material types within groups
- **Regional Variations**: Different material requirements by jurisdiction

### 3. Project-Based Management
EPR activities organized by projects:
- **Product Lines**: Specific product categories or brands
- **Campaigns**: Time-bound compliance initiatives
- **Geographic Scope**: Regional or national programs
- **Multi-Stakeholder**: Involving brands, recyclers, collectors, auditors

## Key Models

### EPR Core Models

#### EprOrganization
```python
class EprOrganization(Base, BaseModel):
    # Link to main organization for billing/subscription
    main_organization_id = Column(BigInteger, ForeignKey('organizations.id'))
    
    # EPR-specific identification
    registration_number = Column(String(100), unique=True)
    license_number = Column(String(100))
    organization_type = Column(String(100))  # producer, importer, distributor
    
    # Compliance status
    is_approved = Column(Boolean, default=False)
    annual_production_volume = Column(DECIMAL(15, 2))
```

#### EprProject
```python
class EprProject(Base, BaseModel):
    organization_id = Column(BigInteger, ForeignKey('epr_organizations.id'))
    
    # Project scope
    project_type = Column(String(100))  # packaging, electronics, textiles
    geographic_scope = Column(String(100))  # national, regional, city
    
    # Targets and compliance
    collection_target = Column(DECIMAL(15, 2))     # tonnes to collect
    recycling_target = Column(DECIMAL(15, 2))      # tonnes to recycle
    target_year = Column(BigInteger)                # compliance year
```

### Supporting Models

#### EprMaterialGroup
```python
class EprMaterialGroup(Base, BaseModel):
    organization_id = Column(BigInteger, ForeignKey('epr_organizations.id'))
    material_main_id = Column(BigInteger, ForeignKey('material_main.id'))
    
    # Targets and fees
    annual_volume_target = Column(DECIMAL(15, 2))
    recycling_rate_target = Column(DECIMAL(5, 2))
    fee_per_tonne = Column(DECIMAL(10, 2))
```

#### User Roles and Assignments
- **EprOrganizationUser**: Core team members
- **EprProjectUser**: Project-specific assignments with roles
- **EprAuditorTransactionAssignment**: Auditor assignments for verification

## EPR Compliance Workflows

### 1. Organization Registration
```python
# Create EPR organization linked to main org
epr_org = EprOrganization(
    main_organization_id=main_org.id,
    name="Green Products EPR Entity",
    organization_type="producer",
    registration_number="EPR2024001",
    annual_production_volume=1500.0  # tonnes
)

# Set up material groups
plastic_group = EprOrganizationMaterialGroup(
    organization_id=epr_org.id,
    material_main_id=plastic_material.id,
    annual_volume_target=800.0,
    recycling_rate_target=75.0,
    fee_per_tonne=150.00
)
```

### 2. Project Creation and Management
```python
# Create EPR project
project = EprProject(
    organization_id=epr_org.id,
    name="2024 Packaging Collection Program",
    project_type="packaging",
    geographic_scope="national",
    collection_target=1000.0,
    recycling_target=750.0,
    target_year=2024
)

# Assign team members
project_user = EprProjectUser(
    project_id=project.id,
    user_location_id=manager.id,
    role="project_manager",
    responsibilities=["target_tracking", "reporting", "stakeholder_management"]
)
```

### 3. Material and Brand Management
```python
# Register brands and products
brand = EprBrand(
    organization_id=epr_org.id,
    name="EcoGreen Products",
    brand_code="ECOGRN",
    is_active=True
)

# Register product lines
product = EprProduct(
    brand_id=brand.id,
    name="EcoGreen Water Bottles",
    material_composition={"PET": 95, "Labels": 3, "Cap": 2},
    estimated_annual_volume=250.0  # tonnes
)
```

### 4. Collection and Processing Tracking
```python
# Link transaction records to EPR
transaction_record.is_epr = True
transaction_record.epr_organization_id = epr_org.id
transaction_record.epr_project_id = project.id

# Track towards targets
current_collected = TransactionRecord.query.filter(
    TransactionRecord.epr_project_id == project.id,
    TransactionRecord.processing_stage == ProcessingStage.COLLECTION
).with_entities(func.sum(TransactionRecord.quantity)).scalar()

project.current_collection_progress = current_collected
project.collection_progress_percentage = (current_collected / project.collection_target) * 100
```

## Multi-Stakeholder Management

### 1. User Roles
- **Producers**: Brand owners responsible for EPR compliance
- **Collectors**: Organizations collecting EPR materials  
- **Recyclers**: Processing facilities handling EPR materials
- **Auditors**: Third-party verification and compliance checking
- **Logistic Assistants**: Transportation and logistics coordinators
- **Regulators**: Government oversight and compliance monitoring

### 2. Role-Based Access Control
```python
# Check user permissions for EPR operations
user_roles = EprProjectUser.query.filter_by(
    project_id=project_id,
    user_location_id=current_user.id
).all()

permissions = []
for role in user_roles:
    permissions.extend(role.responsibilities)

# Permission-based operations
if 'audit_transactions' in permissions:
    # Allow transaction auditing
    pass

if 'manage_targets' in permissions:
    # Allow target modification
    pass
```

### 3. Auditor Assignment System
```python
# Assign auditor to transactions
assignment = EprAuditorTransactionAssignment(
    auditor_id=auditor.id,
    transaction_record_id=transaction_record.id,
    assignment_type="quality_verification",
    priority="high",
    due_date=datetime.utcnow() + timedelta(days=3)
)

# Track auditor workload
auditor_workload = EprAuditorTransactionAssignment.query.filter(
    EprAuditorTransactionAssignment.auditor_id == auditor.id,
    EprAuditorTransactionAssignment.status == "assigned"
).count()
```

## Compliance Reporting and Analytics

### 1. Target Tracking
```python
# Calculate compliance progress
def calculate_compliance_progress(project_id, year):
    project = EprProject.query.get(project_id)
    
    # Collection progress
    collected = TransactionRecord.query.filter(
        TransactionRecord.epr_project_id == project_id,
        extract('year', TransactionRecord.created_date) == year,
        TransactionRecord.processing_stage.in_(['COLLECTION', 'SORTING'])
    ).with_entities(func.sum(TransactionRecord.quantity)).scalar() or 0
    
    # Recycling progress  
    recycled = TransactionRecord.query.filter(
        TransactionRecord.epr_project_id == project_id,
        extract('year', TransactionRecord.created_date) == year,
        TransactionRecord.processing_stage == 'PROCESSING',
        TransactionRecord.recycling_rate > 0
    ).with_entities(func.sum(TransactionRecord.quantity * 
                           TransactionRecord.recycling_rate / 100)).scalar() or 0
    
    return {
        'collection_progress': (collected / project.collection_target) * 100,
        'recycling_progress': (recycled / project.recycling_target) * 100,
        'collected_tonnes': collected,
        'recycled_tonnes': recycled
    }
```

### 2. Regulatory Reporting
```python
# Generate EPR compliance report
def generate_epr_report(organization_id, reporting_period):
    org = EprOrganization.query.get(organization_id)
    projects = org.projects.filter_by(target_year=reporting_period.year).all()
    
    report_data = {
        'organization': org.to_dict(),
        'reporting_period': reporting_period,
        'projects': [],
        'summary': {
            'total_collected': 0,
            'total_recycled': 0,
            'compliance_rate': 0
        }
    }
    
    for project in projects:
        progress = calculate_compliance_progress(project.id, reporting_period.year)
        report_data['projects'].append({
            'project': project.to_dict(),
            'progress': progress
        })
        
        report_data['summary']['total_collected'] += progress['collected_tonnes']
        report_data['summary']['total_recycled'] += progress['recycled_tonnes']
    
    return report_data
```

## Fee Management and Cost Allocation

### 1. Fee Structure
```python
# Calculate EPR fees based on material volumes
def calculate_epr_fees(organization_id, period):
    material_groups = EprOrganizationMaterialGroup.query.filter_by(
        organization_id=organization_id
    ).all()
    
    total_fees = 0
    fee_breakdown = []
    
    for group in material_groups:
        # Get actual volume for period
        actual_volume = get_material_volume(group, period)
        
        # Calculate fees
        fees = actual_volume * group.fee_per_tonne
        total_fees += fees
        
        fee_breakdown.append({
            'material': group.material_main.name,
            'volume': actual_volume,
            'rate': group.fee_per_tonne,
            'fees': fees
        })
    
    return {
        'total_fees': total_fees,
        'breakdown': fee_breakdown
    }
```

### 2. Logistic Assistant Fees
```python
# Manage transportation and logistics costs
laf_setting = EprLogisticAssistantFeeSettings(
    organization_id=epr_org.id,
    base_fee_per_km=2.50,
    fuel_surcharge_percentage=15.0,
    handling_fee_per_tonne=25.00,
    minimum_charge=100.00
)

# Calculate logistics costs
def calculate_logistics_cost(transaction, settings):
    distance = calculate_distance(
        transaction.sender_location,
        transaction.receiver_location
    )
    
    transport_cost = distance * settings.base_fee_per_km
    fuel_surcharge = transport_cost * (settings.fuel_surcharge_percentage / 100)
    handling_cost = transaction.total_weight * settings.handling_fee_per_tonne
    
    total_cost = max(
        transport_cost + fuel_surcharge + handling_cost,
        settings.minimum_charge
    )
    
    return total_cost
```

## Integration Points

### With Main Organization System
- **Billing Integration**: EPR fees flow to main organization billing
- **User Management**: Shared user base with role-based EPR access
- **Subscription Features**: EPR functionality tied to subscription levels

### With Transaction System
- **Material Tracking**: EPR transactions embedded in main transaction flow
- **Compliance Tracking**: Automatic progress calculation from transaction data
- **Audit Trail**: Complete traceability for regulatory compliance

### With Rewards System
- **Incentive Programs**: Reward collectors for EPR material collection
- **Bonus Points**: Higher rewards for EPR-eligible materials
- **Target Achievement**: Special rewards for meeting EPR targets

### With GRI Reporting
- **Sustainability Metrics**: EPR data feeds into sustainability reporting
- **Impact Assessment**: Environmental impact tracking across EPR programs
- **Stakeholder Reporting**: Multi-stakeholder sustainability communications

## Notification and Communication

### 1. Automated Notifications
```python
# Target achievement notifications
if project.collection_progress_percentage >= 100:
    notification = EprNotification(
        recipient_organization_id=project.organization_id,
        notification_type="target_achieved",
        title="Collection Target Achieved!",
        message=f"Project {project.name} has achieved its collection target",
        priority="high"
    )
```

### 2. Stakeholder Communications
- **Progress Updates**: Regular updates to all project stakeholders
- **Audit Notifications**: Alerts for required audits and verifications
- **Regulatory Updates**: Changes in EPR regulations and requirements
- **Performance Reports**: Monthly/quarterly performance summaries

## Best Practices

### 1. Regulatory Compliance
- Maintain up-to-date regulatory requirements by jurisdiction
- Implement automated compliance monitoring and alerting
- Regular audits and third-party verification
- Complete documentation and audit trails

### 2. Multi-Stakeholder Management
- Clear role definitions and responsibility matrices
- Regular stakeholder meetings and updates
- Transparent progress reporting and accountability
- Conflict resolution and issue escalation procedures

### 3. Data Quality and Integrity
- Rigorous data validation for all EPR transactions
- Regular data quality audits and corrections
- Integration with certified scales and measurement systems
- Blockchain or immutable record keeping for critical data

### 4. Performance Optimization
- Efficient target tracking and progress calculations
- Automated fee calculations and billing integration
- Scalable notification and communication systems
- Performance monitoring and optimization

## Future Enhancements

### 1. Advanced Analytics
- Predictive modeling for target achievement
- Cost optimization algorithms
- Material flow optimization
- Market price integration for recycled materials

### 2. Blockchain Integration
- Immutable compliance records
- Smart contracts for automated fee collection
- Transparent multi-stakeholder verification
- Cross-border EPR program interoperability

### 3. IoT Integration
- Real-time material tracking
- Automated quality assessment
- Smart bin monitoring for collection optimization
- Fleet management for logistics optimization

### 4. AI/ML Capabilities
- Automated material sorting and classification
- Predictive maintenance for processing equipment
- Fraud detection and anomaly identification
- Optimization of collection routes and schedules