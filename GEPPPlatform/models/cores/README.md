# Cores Module

## Overview
The cores module provides fundamental reference data and system configurations that serve as the foundation for all other modules in the waste management system. These models represent static or semi-static data that rarely changes and are used across multiple modules.

## Core Concepts

### Geographic Hierarchy
A complete hierarchical location system supporting multi-country operations:
- **LocationCountry** → **LocationRegion** → **LocationProvince** → **LocationDistrict** → **LocationSubdistrict**

This hierarchy enables:
- Precise location tracking for waste transactions
- Regional compliance and reporting
- Logistics optimization
- Multi-jurisdictional operations

### Materials Management
Comprehensive material classification system:
- **MaterialMain**: Primary material categories (plastic, paper, metal, etc.)
- **Material**: Specific material types with detailed properties
- Support for material characteristics like density, contamination levels, and processing requirements

### Financial Infrastructure
Core financial reference data:
- **Bank**: Banking institutions for payment processing
- **Currency**: Multi-currency support for international operations
- **Nationality**: User and organization nationality tracking

### System Configuration
Essential system reference data:
- **Permission**: Granular permission system for access control
- **PermissionType**: Categories of permissions (read, write, admin, etc.)
- **Translation**: Multi-language support for internationalization
- **Locale**: Regional settings and formatting
- **PhoneNumberCountryCode**: International phone number validation

## Key Features

### 1. Hierarchical Data Structure
All geographic and categorical data follows hierarchical patterns, enabling:
- Drill-down reporting and analytics
- Cascading permissions and rules
- Efficient data organization and queries

### 2. Multi-Language Support
- Translation system for all user-facing content
- Locale-specific formatting for dates, numbers, and currencies
- Support for right-to-left languages

### 3. Extensible Design
- JSON fields for custom properties
- Version control for reference data changes
- Audit trails for compliance

### 4. Performance Optimization
- Reference data designed for caching
- Minimal foreign key relationships to reduce join complexity
- Optimized for read-heavy workloads

## Data Flow

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Countries     │────│    Provinces     │────│   Districts     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                                         │
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  Material Main  │────│    Materials     │    │ Subdistricts    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │
┌─────────────────┐    ┌──────────────────┐
│  Organizations  │────│  Transactions    │
└─────────────────┘    └──────────────────┘
```

## Usage Examples

### Location-Based Queries
```python
# Find all provinces in Thailand
provinces = session.query(LocationProvince).join(LocationCountry).filter(
    LocationCountry.name == 'Thailand'
).all()

# Get complete address hierarchy
location = session.query(LocationSubdistrict).options(
    joinedload(LocationSubdistrict.district).joinedload(LocationDistrict.province)
).filter(LocationSubdistrict.id == subdistrict_id).first()
```

### Material Classification
```python
# Find all plastic materials
plastic_materials = session.query(Material).join(MaterialMain).filter(
    MaterialMain.name == 'Plastic'
).all()

# Get material with properties
material = session.query(Material).filter(Material.code == 'PET').first()
density = material.density_kg_m3
contamination_threshold = material.max_contamination_pct
```

### Permission System
```python
# Check user permissions
user_permissions = session.query(Permission).join(user_permissions_table).filter(
    user_permissions_table.c.user_id == user_id
).all()

# Hierarchical permission check
has_admin = any(p.type.name == 'admin' for p in user_permissions)
```

## Best Practices

### 1. Reference Data Management
- Use consistent naming conventions across all reference data
- Implement proper validation for codes and identifiers
- Maintain data integrity through foreign key constraints

### 2. Caching Strategy
- Cache frequently accessed reference data (countries, materials, permissions)
- Implement cache invalidation when reference data changes
- Use read replicas for reference data queries

### 3. Internationalization
- Always provide translations for user-facing data
- Use locale-appropriate formatting for all displays
- Consider cultural differences in data presentation

### 4. Data Governance
- Establish clear ownership for each reference data type
- Implement approval processes for reference data changes
- Maintain comprehensive documentation for all codes and classifications

## Integration Points

### With Other Modules
- **Users**: Location hierarchy, permissions, nationalities
- **Transactions**: Materials, locations, currencies
- **Organizations**: Countries, provinces, banks
- **EPR**: Materials, locations for compliance reporting
- **GRI**: Materials, locations for sustainability reporting
- **Rewards**: Currencies, locations for reward programs

### External Systems
- Import/export capabilities for reference data synchronization
- API endpoints for third-party system integration
- Bulk update procedures for large-scale data changes

## Maintenance

### Regular Tasks
- Review and update material classifications based on industry standards
- Validate geographic data against official sources
- Update currency exchange rates and banking information
- Audit permission structures for security compliance

### Data Quality
- Implement validation rules for all reference data
- Regular data quality checks and cleanup procedures
- Monitoring for orphaned or inconsistent data
- Performance monitoring for reference data queries

## Security Considerations

- Reference data access controls to prevent unauthorized modifications
- Audit logging for all reference data changes
- Backup and recovery procedures for critical reference data
- Data encryption for sensitive reference information (banking details)