# Users Module

## Overview
The users module implements a unified user-location architecture that consolidates users, locations, and business units into a single flexible model. This design supports complex organizational hierarchies while maintaining simplicity for basic use cases.

## Core Concepts

### Unified User-Location Model
The **UserLocation** model serves dual purposes through boolean flags:
- **`is_user=True`**: Entity can authenticate and use the system
- **`is_location=True`**: Entity can serve as a waste transaction point
- **Both flags can be True**: A user who also represents a physical location

### Organizational Tree Structure
Multi-level organizational hierarchies through:
- **Parent-Child Relationships**: Direct hierarchical links via `parent_user_id`
- **Materialized Path**: Efficient tree traversal using `organization_path`
- **Organization Levels**: Depth tracking with `organization_level`
- **Many-to-Many Subusers**: Flexible cross-organizational relationships via `user_subusers` association table

## Architecture Benefits

### 1. Simplified Data Model
- Single table for users, locations, and business units
- Eliminates complex joins between separate user and location tables
- Reduces data duplication and synchronization issues

### 2. Flexible Business Models
- **Individual Users**: `is_user=True, is_location=False`
- **Physical Locations**: `is_user=False, is_location=True`
- **Location Managers**: `is_user=True, is_location=True`
- **Virtual Organizations**: `is_user=False, is_location=False` (for hierarchy only)

### 3. Scalable Hierarchies
- Support for unlimited organizational depth
- Efficient tree operations through materialized paths
- Cross-organizational relationships via subuser associations

## Key Models

### UserLocation
Central entity combining user and location functionality:

```python
class UserLocation(Base, BaseModel):
    # Dual functionality flags
    is_user = Column(Boolean, default=False)      # Can login/authenticate
    is_location = Column(Boolean, default=False)  # Can be transaction node
    
    # Organizational hierarchy
    parent_user_id = Column(BigInteger, ForeignKey('user_locations.id'))
    organization_level = Column(Integer, default=0)
    organization_path = Column(Text)  # e.g., "/1/5/12/"
    
    # Organization linkage
    organization_id = Column(ForeignKey('organizations.id'))
```

### Supporting Models
- **UserRole**: Platform-specific user roles and permissions
- **UserBank**: Banking information for payments and rewards
- **UserSubscription**: Subscription management per organization
- **UserInputChannel**: Integration channels and configurations

## Organizational Patterns

### 1. Corporate Hierarchy
```
Gepp Corporation (is_user=False, is_location=False)
├── Regional Office Bangkok (is_user=False, is_location=True)
│   ├── John Smith - Regional Manager (is_user=True, is_location=False)
│   └── Bangkok Warehouse (is_user=False, is_location=True)
│       └── Warehouse Staff (is_user=True, is_location=True)
└── Regional Office Chiang Mai (is_user=False, is_location=True)
    └── Processing Center (is_user=False, is_location=True)
```

### 2. SME Structure
```
Small Recycling Company (is_user=True, is_location=True)
├── Owner/Operator (is_user=True, is_location=False)
└── Part-time Staff (is_user=True, is_location=False)
```

### 3. Franchise Network
```
Franchise Parent (is_user=False, is_location=False)
├── Franchise Location A (is_user=True, is_location=True)
├── Franchise Location B (is_user=True, is_location=True)
└── Corporate Support (is_user=True, is_location=False)
```

## Data Relationships

### Authentication & Authorization
```python
# Check if entity can login
if user_location.is_user and user_location.password_hash:
    # Allow authentication
    
# Get user permissions
roles = user_location.organization.user_roles
permissions = [role.permissions for role in roles]
```

### Transaction Capability
```python
# Check if entity can be transaction endpoint
if user_location.is_location:
    # Can send/receive waste transactions
    transactions_sent = Transaction.query.filter_by(
        sender_user_location_id=user_location.id
    ).all()
```

### Hierarchy Navigation
```python
# Get all descendants using materialized path
descendants = UserLocation.query.filter(
    UserLocation.organization_path.like(f"{parent.organization_path}{parent.id}/%")
).all()

# Get direct children
children = UserLocation.query.filter_by(
    parent_user_id=parent.id
).all()

# Get organization root
root = UserLocation.query.filter(
    UserLocation.organization_id == org_id,
    UserLocation.parent_user_id.is_(None)
).first()
```

## Use Cases

### 1. Waste Collection Network
- **Collection Company**: Parent organization
- **Collection Routes**: Location entities for route management
- **Drivers**: User entities assigned to routes
- **Collection Points**: Location entities for pickup points

### 2. Processing Facility
- **Facility**: User-location entity (can login to manage operations)
- **Processing Lines**: Location entities for tracking material flow
- **Operators**: User entities for line management
- **Quality Control**: User entities for inspection processes

### 3. Multi-Site Enterprise
- **Corporate HQ**: Parent organization entity
- **Regional Offices**: Location entities with regional managers (users)
- **Local Facilities**: Location entities with local staff (users)
- **Mobile Teams**: User entities that work across multiple locations

## Best Practices

### 1. Hierarchy Design
- Keep organizational levels shallow when possible (max 5-6 levels)
- Use clear naming conventions for different entity types
- Implement proper access controls based on hierarchy position

### 2. Flag Management
- Always validate flag combinations make business sense
- Implement database constraints to prevent invalid states
- Use clear business rules for when flags should be set

### 3. Performance Optimization
- Index materialized paths for efficient tree queries
- Cache frequently accessed hierarchy data
- Use appropriate query strategies for different hierarchy operations

### 4. Data Integrity
- Implement proper cascading deletes for hierarchy changes
- Validate organizational moves don't create cycles
- Maintain path consistency during hierarchy updates

## Security Considerations

### Multi-Tenancy
- All user data is isolated by organization_id
- Cross-organizational access requires explicit permissions
- Hierarchy navigation respects organizational boundaries

### Access Control
- Role-based permissions at organization level
- Hierarchy-aware permission inheritance
- Location-specific access controls for transaction operations

### Data Protection
- Sensitive user data (passwords, banking) properly encrypted
- Audit trails for all user account changes
- GDPR compliance for user data management

## Integration Points

### With Other Modules
- **Transactions**: Users as senders/receivers, locations as transaction points
- **Rewards**: User points, redemptions, and tier management
- **EPR**: User assignments to EPR projects and responsibilities
- **GRI**: User roles in sustainability reporting and goal management
- **Subscriptions**: User access to organizational subscription features

### External Systems
- **Identity Providers**: SSO integration for enterprise users
- **HR Systems**: Employee data synchronization
- **CRM Systems**: Customer and vendor information integration
- **Geographic Systems**: Location data validation and enrichment