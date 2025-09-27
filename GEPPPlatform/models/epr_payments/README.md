# EPR Payments Module - Financial Management for Extended Producer Responsibility

## Overview
The EPR Payments module manages the complex financial flows within Extended Producer Responsibility programs. It handles fee calculations, payment processing, cost allocation among stakeholders, and financial compliance reporting for EPR organizations and their associated projects.

## Core Concepts

### EPR Financial Ecosystem
EPR programs involve multiple financial flows between various stakeholders:
- **Producer Fees**: Payments from producers for their EPR obligations
- **Collection Incentives**: Payments to collectors for gathering EPR materials
- **Processing Payments**: Payments to recyclers and processors
- **Logistic Assistance Fees**: Transportation and handling cost reimbursements
- **Administrative Costs**: Program management and oversight expenses
- **Compliance Penalties**: Fees for non-compliance with EPR targets

### Payment Flow Architecture
```
EPR Producers
    ↓ (EPR Fees)
EPR Program Pool
    ↓ (Distributed to)
    ├── Collection Partners (Collection Fees)
    ├── Processing Partners (Processing Fees)
    ├── Logistics Providers (Transportation Fees)
    └── Program Administration (Management Fees)
```

### Multi-Level Fee Structures
- **Organization Level**: Base EPR membership and compliance fees
- **Project Level**: Specific project-based fee calculations
- **Material Level**: Per-material-type fee structures
- **Performance Level**: Variable fees based on achievement rates

## Key Models

### EPR Payment Transaction
```python
class EprPaymentTransaction(Base, BaseModel):
    # Financial details
    amount = Column(DECIMAL(15, 2), nullable=False)
    currency = Column(String(3), default='THB')
    transaction_type = Column(SQLEnum(EprPaymentTransactionType))
    
    # Stakeholder relationships
    payer_organization_id = Column(BigInteger, ForeignKey('epr_organizations.id'))
    payee_organization_id = Column(BigInteger, ForeignKey('epr_organizations.id'))
    
    # Context linking
    epr_project_id = Column(BigInteger, ForeignKey('epr_projects.id'))
    related_transaction_record_id = Column(BigInteger, ForeignKey('transaction_records.id'))
    
    # Payment status and processing
    status = Column(String(50), default='pending')
    payment_method = Column(String(50))
    processing_date = Column(DateTime)
```

### Payment Transaction Records
```python
class EprPaymentTransactionRecord(Base, BaseModel):
    payment_transaction_id = Column(BigInteger, ForeignKey('epr_payment_transactions.id'))
    
    # Material and quantity details
    material_id = Column(BigInteger, ForeignKey('materials.id'))
    quantity = Column(DECIMAL(15, 2), nullable=False)
    unit_price = Column(DECIMAL(10, 4))  # Price per unit (kg, tonne, etc.)
    
    # Fee calculation details
    base_fee = Column(DECIMAL(10, 2))
    performance_bonus = Column(DECIMAL(10, 2))
    quality_adjustment = Column(DECIMAL(10, 2))
    distance_adjustment = Column(DECIMAL(10, 2))
    
    # Calculation metadata
    fee_calculation_data = Column(JSON)
```

## Fee Calculation Engine

### 1. Base Fee Structure
```python
def calculate_base_epr_fee(material_id, quantity, organization_id):
    """Calculate base EPR fee for material volume"""
    
    # Get material group fee rate
    material_group = EprOrganizationMaterialGroup.query.filter_by(
        organization_id=organization_id,
        material_main_id=get_material_main_id(material_id)
    ).first()
    
    if not material_group:
        raise ValueError(f"No fee structure found for material {material_id}")
    
    base_fee = quantity * material_group.fee_per_tonne
    
    return {
        'base_fee': base_fee,
        'rate': material_group.fee_per_tonne,
        'quantity': quantity,
        'material_group_id': material_group.id
    }
```

### 2. Performance-Based Adjustments
```python
def calculate_performance_adjustment(transaction_record, project):
    """Calculate performance-based fee adjustments"""
    
    adjustments = {
        'quality_bonus': 0,
        'target_achievement_bonus': 0,
        'efficiency_bonus': 0
    }
    
    # Quality bonus for clean materials
    if transaction_record.material_condition == MaterialCondition.CLEAN:
        adjustments['quality_bonus'] = transaction_record.quantity * 5.0  # 5 THB/kg bonus
    
    # Target achievement bonus
    if project.collection_progress_percentage >= 100:
        adjustments['target_achievement_bonus'] = transaction_record.quantity * 2.0
    
    # Processing efficiency bonus
    if transaction_record.recycling_rate >= 90:
        adjustments['efficiency_bonus'] = transaction_record.quantity * 3.0
    
    return adjustments
```

### 3. Geographic and Logistic Adjustments
```python
def calculate_logistic_adjustment(sender_location, receiver_location, settings):
    """Calculate distance-based logistic fee adjustments"""
    
    # Calculate distance
    distance_km = calculate_distance(sender_location.coordinates, receiver_location.coordinates)
    
    # Base transportation fee
    transport_fee = distance_km * settings.base_fee_per_km
    
    # Fuel surcharge
    fuel_surcharge = transport_fee * (settings.fuel_surcharge_percentage / 100)
    
    # Remote area surcharge
    remote_surcharge = 0
    if distance_km > 100:  # Over 100km considered remote
        remote_surcharge = transport_fee * 0.25  # 25% surcharge
    
    total_logistic_fee = transport_fee + fuel_surcharge + remote_surcharge
    
    return {
        'transport_fee': transport_fee,
        'fuel_surcharge': fuel_surcharge,
        'remote_surcharge': remote_surcharge,
        'total_logistic_fee': total_logistic_fee,
        'distance_km': distance_km
    }
```

## Payment Processing Workflows

### 1. EPR Fee Collection (From Producers)
```python
def process_producer_epr_payment(organization_id, period):
    """Process EPR fee payment from producer organization"""
    
    # Calculate total EPR obligation
    obligation = calculate_epr_obligation(organization_id, period)
    
    # Create payment transaction
    payment = EprPaymentTransaction(
        payer_organization_id=organization_id,
        payee_organization_id=program_administrator_id,
        amount=obligation['total_amount'],
        transaction_type=EprPaymentTransactionType.EPR_FEE,
        description=f"EPR fee for period {period}",
        due_date=period.end_date + timedelta(days=30)
    )
    
    # Create detailed payment records
    for material_obligation in obligation['material_breakdown']:
        payment_record = EprPaymentTransactionRecord(
            payment_transaction_id=payment.id,
            material_id=material_obligation['material_id'],
            quantity=material_obligation['volume'],
            unit_price=material_obligation['fee_rate'],
            base_fee=material_obligation['base_fee'],
            fee_calculation_data=material_obligation['calculation_details']
        )
    
    return payment
```

### 2. Incentive Payments (To Collectors/Processors)
```python
def process_collection_incentive_payment(transaction_record):
    """Process incentive payment for EPR material collection"""
    
    if not transaction_record.is_epr:
        return None
    
    # Get applicable incentive rates
    project = EprProject.query.get(transaction_record.epr_project_id)
    incentive_settings = project.collection_incentive_settings
    
    # Calculate base incentive
    base_incentive = transaction_record.quantity * incentive_settings.base_rate_per_kg
    
    # Apply performance adjustments
    performance_adj = calculate_performance_adjustment(transaction_record, project)
    total_bonus = sum(performance_adj.values())
    
    # Apply logistic adjustments if applicable
    logistic_adj = 0
    if incentive_settings.includes_logistics:
        sender_location = transaction_record.transaction.sender_user_location
        receiver_location = transaction_record.transaction.receiver_user_location
        logistic_calculation = calculate_logistic_adjustment(
            sender_location, receiver_location, incentive_settings.logistic_settings
        )
        logistic_adj = logistic_calculation['total_logistic_fee']
    
    total_payment = base_incentive + total_bonus + logistic_adj
    
    # Create payment transaction
    payment = EprPaymentTransaction(
        payer_organization_id=project.organization_id,  # EPR organization pays
        payee_organization_id=transaction_record.transaction.sender_user_location.organization_id,
        amount=total_payment,
        transaction_type=EprPaymentTransactionType.COLLECTION_INCENTIVE,
        related_transaction_record_id=transaction_record.id,
        epr_project_id=project.id
    )
    
    return payment
```

### 3. Processing Fee Distribution
```python
def process_processing_fee_payment(transaction_record):
    """Process payment for EPR material processing"""
    
    if transaction_record.processing_stage != ProcessingStage.PROCESSING:
        return None
    
    project = EprProject.query.get(transaction_record.epr_project_id)
    processing_settings = project.processing_fee_settings
    
    # Base processing fee
    base_fee = transaction_record.quantity * processing_settings.base_rate_per_kg
    
    # Recycling efficiency bonus
    recycling_bonus = 0
    if transaction_record.recycling_rate:
        bonus_rate = processing_settings.efficiency_bonus_rate
        recycling_bonus = (transaction_record.recycling_rate / 100) * base_fee * bonus_rate
    
    # Quality bonus for clean output
    quality_bonus = 0
    if transaction_record.output_quality_grade in ['A', 'B']:
        quality_bonus = base_fee * processing_settings.quality_bonus_percentage
    
    total_payment = base_fee + recycling_bonus + quality_bonus
    
    payment = EprPaymentTransaction(
        payer_organization_id=project.organization_id,
        payee_organization_id=transaction_record.transaction.receiver_user_location.organization_id,
        amount=total_payment,
        transaction_type=EprPaymentTransactionType.PROCESSING_FEE,
        related_transaction_record_id=transaction_record.id
    )
    
    return payment
```

## Financial Reporting and Analytics

### 1. Payment Summary Reports
```python
def generate_payment_summary_report(organization_id, period):
    """Generate comprehensive payment summary for EPR organization"""
    
    payments_in = EprPaymentTransaction.query.filter(
        EprPaymentTransaction.payee_organization_id == organization_id,
        EprPaymentTransaction.processing_date.between(period.start_date, period.end_date),
        EprPaymentTransaction.status == 'completed'
    ).all()
    
    payments_out = EprPaymentTransaction.query.filter(
        EprPaymentTransaction.payer_organization_id == organization_id,
        EprPaymentTransaction.processing_date.between(period.start_date, period.end_date),
        EprPaymentTransaction.status == 'completed'
    ).all()
    
    summary = {
        'period': period,
        'total_received': sum(p.amount for p in payments_in),
        'total_paid': sum(p.amount for p in payments_out),
        'net_position': sum(p.amount for p in payments_in) - sum(p.amount for p in payments_out),
        'payment_breakdown': {
            'epr_fees_received': sum(p.amount for p in payments_in 
                                   if p.transaction_type == EprPaymentTransactionType.EPR_FEE),
            'collection_incentives_paid': sum(p.amount for p in payments_out 
                                            if p.transaction_type == EprPaymentTransactionType.COLLECTION_INCENTIVE),
            'processing_fees_paid': sum(p.amount for p in payments_out 
                                      if p.transaction_type == EprPaymentTransactionType.PROCESSING_FEE),
            'logistic_fees_paid': sum(p.amount for p in payments_out 
                                    if p.transaction_type == EprPaymentTransactionType.LOGISTIC_ASSISTANCE)
        }
    }
    
    return summary
```

### 2. Cost per Tonne Analytics
```python
def calculate_cost_per_tonne_analytics(project_id, period):
    """Calculate cost efficiency metrics for EPR project"""
    
    project = EprProject.query.get(project_id)
    
    # Get total material volumes
    total_collected = TransactionRecord.query.filter(
        TransactionRecord.epr_project_id == project_id,
        TransactionRecord.processing_stage == ProcessingStage.COLLECTION,
        TransactionRecord.created_date.between(period.start_date, period.end_date)
    ).with_entities(func.sum(TransactionRecord.quantity)).scalar() or 0
    
    total_processed = TransactionRecord.query.filter(
        TransactionRecord.epr_project_id == project_id,
        TransactionRecord.processing_stage == ProcessingStage.PROCESSING,
        TransactionRecord.created_date.between(period.start_date, period.end_date)
    ).with_entities(func.sum(TransactionRecord.quantity)).scalar() or 0
    
    # Get total costs
    total_costs = EprPaymentTransaction.query.filter(
        EprPaymentTransaction.payer_organization_id == project.organization_id,
        EprPaymentTransaction.epr_project_id == project_id,
        EprPaymentTransaction.processing_date.between(period.start_date, period.end_date),
        EprPaymentTransaction.status == 'completed'
    ).with_entities(func.sum(EprPaymentTransaction.amount)).scalar() or 0
    
    analytics = {
        'cost_per_tonne_collected': total_costs / total_collected if total_collected > 0 else 0,
        'cost_per_tonne_processed': total_costs / total_processed if total_processed > 0 else 0,
        'collection_efficiency': total_collected / project.collection_target * 100,
        'processing_efficiency': total_processed / project.recycling_target * 100,
        'total_program_cost': total_costs,
        'volumes': {
            'collected': total_collected,
            'processed': total_processed,
            'targets': {
                'collection': project.collection_target,
                'processing': project.recycling_target
            }
        }
    }
    
    return analytics
```

## Assistant Fee Management

### 1. Logistic Assistant Fee Settings
```python
class EprProjectUserAssistantFeeSetting(Base, BaseModel):
    project_user_id = Column(BigInteger, ForeignKey('epr_project_users.id'))
    
    # Fee calculation method
    calculation_method = Column(SQLEnum(EprProjectAssistantFeeCalculationMethodType))
    
    # Rate structures
    fixed_rate_per_transaction = Column(DECIMAL(10, 2))
    percentage_of_transaction_value = Column(DECIMAL(5, 2))
    tiered_rates = Column(JSON)  # Volume-based tiered rates
    
    # Geographic adjustments
    base_distance_km = Column(DECIMAL(10, 2))
    additional_distance_rate = Column(DECIMAL(5, 2))
    remote_area_multiplier = Column(DECIMAL(3, 2))
    
    # Performance incentives
    quality_bonus_percentage = Column(DECIMAL(5, 2))
    efficiency_bonus_threshold = Column(DECIMAL(5, 2))
    on_time_delivery_bonus = Column(DECIMAL(10, 2))
```

### 2. Monthly Assistant Fee Processing
```python
def process_monthly_assistant_fees(project_id, month, year):
    """Process monthly fees for logistic assistants"""
    
    project_users = EprProjectUser.query.filter(
        EprProjectUser.project_id == project_id,
        EprProjectUser.role.in_(['logistic_assistant', 'collection_coordinator'])
    ).all()
    
    for project_user in project_users:
        # Get assistant's transactions for the month
        user_transactions = get_user_monthly_transactions(project_user.user_location_id, month, year)
        
        # Calculate fees based on settings
        fee_settings = project_user.assistant_fee_setting
        total_fees = 0
        
        for transaction in user_transactions:
            transaction_fee = calculate_assistant_transaction_fee(transaction, fee_settings)
            total_fees += transaction_fee
            
            # Record individual fee
            fee_record = EprProjectUserAssistantFee(
                project_user_id=project_user.id,
                transaction_record_id=transaction.id,
                base_fee=transaction_fee['base_fee'],
                distance_adjustment=transaction_fee['distance_adjustment'],
                performance_bonus=transaction_fee['performance_bonus'],
                total_amount=transaction_fee['total']
            )
        
        # Create monthly payment
        monthly_payment = EprPaymentTransaction(
            payer_organization_id=project.organization_id,
            payee_organization_id=project_user.user_location.organization_id,
            amount=total_fees,
            transaction_type=EprPaymentTransactionType.LOGISTIC_ASSISTANCE,
            epr_project_id=project_id,
            description=f"Monthly assistant fees for {month}/{year}"
        )
```

## Integration Points

### With EPR Core Module
- **Project Linkage**: All payments tied to specific EPR projects
- **Organization Hierarchy**: Payments flow between EPR organizations
- **Material Tracking**: Fee calculations based on material volumes and types
- **Compliance Integration**: Payment completion affects compliance status

### With Transaction Module
- **Transaction-Based Payments**: Each transaction record can trigger payments
- **Performance Metrics**: Payment amounts based on transaction quality and efficiency
- **Audit Trail**: Complete traceability from transaction to payment

### With Main Billing System
- **Consolidated Billing**: EPR payments integrated with main organization billing
- **Multi-Currency Support**: Handle payments in different currencies
- **Tax and Accounting**: Integration with accounting systems for tax compliance

### With Rewards Module
- **Incentive Alignment**: EPR payments can supplement reward point systems
- **Performance Bonuses**: Additional rewards for exceptional EPR performance
- **User Motivation**: Financial incentives combined with gamification

## Compliance and Audit

### 1. Financial Audit Trails
- Complete payment history with immutable records
- Multi-level approval workflows for large payments
- Integration with external auditing systems
- Regulatory reporting capabilities

### 2. Fraud Prevention
- Automated anomaly detection for unusual payment patterns
- Multi-factor approval for high-value transactions
- Regular reconciliation between payments and transaction records
- External verification for critical payments

### 3. Regulatory Compliance
- Automated calculation of regulatory fees and penalties
- Integration with government EPR reporting systems
- Tax compliance for cross-border payments
- Anti-money laundering (AML) compliance

## Best Practices

### 1. Fee Structure Design
- Transparent and predictable fee calculations
- Performance-based incentives to drive behavior
- Regular review and optimization of fee structures
- Stakeholder input in fee structure development

### 2. Payment Processing
- Automated payment processing where possible
- Clear payment terms and conditions
- Efficient dispute resolution processes
- Regular payment performance monitoring

### 3. Financial Management
- Cash flow forecasting and management
- Risk assessment for payment defaults
- Currency hedging for multi-currency operations
- Regular financial performance reviews

### 4. Technology Infrastructure
- Scalable payment processing systems
- Real-time payment status tracking
- Integration with banking and payment systems
- Robust security and data protection measures