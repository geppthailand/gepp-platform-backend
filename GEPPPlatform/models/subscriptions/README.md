# Subscriptions Module

## Overview
The subscriptions module manages organizational accounts, subscription packages, and feature access control. It provides the foundation for multi-tenant SaaS operations with flexible subscription models and comprehensive organizational information management.

## Core Concepts

### Organization Management
**Organization** and **OrganizationInfo** work together to provide:
- **Organization**: Core entity with basic identification
- **OrganizationInfo**: Comprehensive business information, contact details, and metadata

This separation allows for:
- Lightweight organization references throughout the system
- Detailed information storage without performance impact
- Flexible information expansion without affecting core relationships

### Subscription System
Multi-tier subscription model supporting:
- **Global Packages**: Standard packages available to all organizations
- **Custom Packages**: Organization-specific packages with tailored features
- **Permission-Based Access**: Granular feature control through permission mappings

## Key Models

### Organization
Core organizational entity:
```python
class Organization(Base, BaseModel):
    name = Column(String(255))
    description = Column(Text)
    organization_info_id = Column(BigInteger, ForeignKey('organization_info.id'))
```

### OrganizationInfo
Comprehensive organizational details:
- **Business Information**: Industry, type, registration details
- **Contact Information**: Addresses, phone numbers, email
- **Legal Information**: Tax ID, business certificates
- **Geographic Location**: Full address hierarchy
- **Operational Data**: Footprint, capacity, project details

### SubscriptionPackage
Flexible subscription model:
```python
class SubscriptionPackage(Base, BaseModel):
    organization_id = Column(BigInteger, ForeignKey('organizations.id'))  # Nullable for global
    is_global = Column(Integer, default=1)  # Global vs organization-specific
    price = Column(DECIMAL(10, 2))
    duration_days = Column(Integer)
```

### SubscriptionPermission
Permission mapping for packages:
- Links subscription packages to specific system permissions
- Enables fine-grained feature access control
- Supports permission inheritance and overrides

## Subscription Models

### 1. Global Packages
Standard packages available to all organizations:
- **Starter**: Basic waste tracking and reporting
- **Professional**: Advanced analytics and EPR compliance
- **Enterprise**: Full feature set with custom integrations

### 2. Custom Packages
Organization-specific packages for:
- **Large Enterprises**: Tailored feature sets and pricing
- **Government Agencies**: Compliance-focused packages
- **Industry Specific**: Packages designed for specific waste streams

### 3. Feature-Based Access
Permissions control access to:
- **Modules**: EPR, GRI, Rewards system access
- **Operations**: Transaction creation, reporting, user management
- **Data**: Access levels for sensitive information
- **Integrations**: Third-party system connections

## Organization Information Architecture

### Business Profile
```python
# Basic company identification
company_name = "Green Waste Solutions Ltd."
company_name_th = "บริษัท กรีน เวสท์ โซลูชั่นส์ จำกัด"
company_name_en = "Green Waste Solutions Limited"
display_name = "GWS"

# Business classification
business_type = "Waste Management Service Provider"
business_industry = "Environmental Services"
business_sub_industry = "Industrial Waste Processing"
account_type = "B2B Service Provider"
```

### Legal and Compliance
```python
# Legal identifiers
tax_id = "0123456789012"
national_id = "1234567890123"
business_registration_certificate = "path/to/certificate.pdf"

# Registration tracking
application_date = "2024-01-15"
approval_status = "approved"
```

### Geographic Information
Full address hierarchy integration:
- Country → Province → District → Subdistrict
- GPS coordinates for precise location
- Service area definitions
- Logistics optimization data

## Subscription Lifecycle

### 1. Organization Onboarding
```python
# Create organization
org = Organization(name="New Waste Company")
org_info = OrganizationInfo(
    company_name="New Waste Company Ltd.",
    business_type="Waste Collector",
    tax_id="1234567890123"
)

# Assign starter package
starter_package = SubscriptionPackage.query.filter_by(
    name="Starter", is_global=1
).first()

subscription = UserSubscription(
    user_location_id=admin_user.id,
    organization_id=org.id,
    subscription_package_id=starter_package.id,
    start_date=datetime.utcnow(),
    end_date=datetime.utcnow() + timedelta(days=starter_package.duration_days)
)
```

### 2. Subscription Management
```python
# Check active subscription
active_sub = UserSubscription.query.filter(
    UserSubscription.organization_id == org_id,
    UserSubscription.end_date > datetime.utcnow(),
    UserSubscription.is_active == True
).first()

# Get available features
if active_sub:
    permissions = active_sub.subscription_package.permissions
    available_features = [perm.permission.name for perm in permissions]
```

### 3. Upgrade/Downgrade
```python
# Upgrade to professional
professional_package = SubscriptionPackage.query.filter_by(
    name="Professional", is_global=1
).first()

# Calculate prorated pricing
remaining_days = (current_sub.end_date - datetime.utcnow()).days
credit = (remaining_days / current_sub.subscription_package.duration_days) * \
         current_sub.subscription_package.price
new_price = professional_package.price - credit
```

## Permission System Integration

### Feature Gating
```python
def require_permission(permission_name):
    def decorator(func):
        def wrapper(*args, **kwargs):
            user_permissions = get_user_permissions(current_user)
            if permission_name not in user_permissions:
                raise PermissionError(f"Permission {permission_name} required")
            return func(*args, **kwargs)
        return wrapper
    return decorator

@require_permission('epr.create_project')
def create_epr_project():
    # Only available to users with EPR permissions
    pass
```

### Module Access Control
- **EPR Module**: Requires 'epr.access' permission
- **GRI Reporting**: Requires 'gri.report' permission  
- **Rewards Management**: Requires 'rewards.manage' permission
- **Advanced Analytics**: Requires 'analytics.advanced' permission

## Multi-Tenancy Architecture

### Data Isolation
- All data scoped by organization_id
- Cross-organizational queries explicitly controlled
- Automatic filtering at application level

### Resource Allocation
- Subscription-based resource limits
- Usage tracking and quota enforcement
- Performance isolation between organizations

### Customization Support
- Organization-specific configurations
- Custom branding and theming
- Localized content and terminology

## Business Models Supported

### 1. SaaS Platform
- Monthly/annual subscription billing
- Feature-tier based pricing
- Usage-based billing for transaction volumes

### 2. Enterprise Licensing
- Custom contract terms and pricing
- On-premises deployment options
- Dedicated support and services

### 3. Government/NGO
- Special pricing for non-profits
- Compliance-focused feature sets
- Multi-agency collaboration tools

### 4. Channel Partners
- White-label deployment options
- Partner-specific customizations
- Revenue sharing models

## Integration Points

### Billing Systems
- Automated subscription billing
- Usage metering and reporting
- Payment processing integration
- Invoice generation and delivery

### CRM Integration
- Customer lifecycle management
- Sales pipeline tracking
- Support ticket integration
- Customer success metrics

### Identity Management
- Single sign-on (SSO) integration
- Multi-factor authentication
- User provisioning and deprovisioning
- Role-based access control

## Analytics and Reporting

### Subscription Metrics
- Monthly recurring revenue (MRR)
- Customer acquisition cost (CAC)
- Churn rate and retention analysis
- Feature adoption rates

### Organization Insights
- Usage patterns by organization size
- Geographic distribution analysis
- Industry vertical performance
- Feature utilization reporting

## Best Practices

### 1. Subscription Design
- Keep package structures simple and understandable
- Provide clear upgrade paths between tiers
- Include trial periods for evaluation
- Regular review and optimization of package offerings

### 2. Organization Management
- Maintain data quality through validation
- Implement proper backup and recovery
- Regular data cleanup and archival
- Compliance with data protection regulations

### 3. Permission Management
- Principle of least privilege
- Regular permission audits
- Clear documentation of permission requirements
- Automated permission assignment based on roles

### 4. Multi-Tenancy
- Strong data isolation enforcement
- Performance monitoring per organization
- Resource usage tracking and alerting
- Scalable architecture for growth