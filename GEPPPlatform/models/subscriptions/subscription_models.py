"""
Subscription and permission models
"""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, Boolean, Integer, JSON, Table
from sqlalchemy.orm import relationship
from ..base import Base, BaseModel
from ..cores.roles import subscription_permissions

# Association tables for many-to-many relationships
organization_role_permissions = Table(
    'organization_role_permissions',
    Base.metadata,
    Column('role_id', ForeignKey('organization_roles.id'), primary_key=True),
    Column('permission_id', ForeignKey('organization_permissions.id'), primary_key=True)
)


class SubscriptionPlan(Base, BaseModel):
    """Subscription plans available in the system"""
    __tablename__ = 'subscription_plans'
    
    name = Column(String(100), unique=True, nullable=False)  # e.g., 'free', 'starter', 'professional', 'enterprise'
    display_name = Column(String(255))
    description = Column(Text)
    price_monthly = Column(Integer, default=0)  # Price in cents
    price_yearly = Column(Integer, default=0)
    
    # Limits
    max_users = Column(Integer, default=1)
    max_transactions_monthly = Column(Integer, default=100)
    max_storage_gb = Column(Integer, default=1)
    max_api_calls_daily = Column(Integer, default=1000)
    
    # Features as JSON
    features = Column(JSON)  # JSON array of feature strings
    
    # Relationships
    subscriptions = relationship("Subscription", back_populates="plan")
    
class Subscription(Base, BaseModel):
    """Active subscriptions for organizations"""
    __tablename__ = 'subscriptions'
    
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    plan_id = Column(BigInteger, ForeignKey('subscription_plans.id'), nullable=False)
    
    status = Column(String(50), default='active')  # active, suspended, cancelled, expired
    trial_ends_at = Column(String(50))
    current_period_starts_at = Column(String(50))
    current_period_ends_at = Column(String(50))
    
    # Usage tracking
    users_count = Column(Integer, default=1)
    transactions_count_this_month = Column(Integer, default=0)
    storage_used_gb = Column(Integer, default=0)
    api_calls_today = Column(Integer, default=0)

    # Transaction and AI audit limits
    create_transaction_limit = Column(Integer, default=100)
    create_transaction_usage = Column(Integer, default=0)
    ai_audit_limit = Column(Integer, default=10)
    ai_audit_usage = Column(Integer, default=0)
    
    # Relationships
    organization = relationship("Organization", foreign_keys=[organization_id])
    plan = relationship("SubscriptionPlan", back_populates="subscriptions")
    permissions = relationship("SystemPermission", secondary=subscription_permissions, back_populates="subscriptions")


class OrganizationPermission(Base, BaseModel):
    """Organization-level permissions that can be assigned to roles within an organization"""
    __tablename__ = 'organization_permissions'
    
    code = Column(String(100), unique=True, nullable=False)  # e.g., 'transaction.create'
    name = Column(String(255))
    description = Column(Text)
    category = Column(String(100))  # e.g., 'transaction', 'user_management', 'reporting'
    
    # Which roles have this permission
    roles = relationship("OrganizationRole", secondary=organization_role_permissions, back_populates="permissions")

class OrganizationRole(Base, BaseModel):
    """Roles within an organization"""
    __tablename__ = 'organization_roles'

    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    key = Column(String(50), nullable=False)  # e.g., 'admin', 'data_input', 'auditor', 'viewer'
    name = Column(String(100), nullable=False)  # e.g., 'Administrator', 'Data Input Specialist'
    description = Column(Text)
    is_system = Column(Boolean, default=False)  # True for default roles that can't be deleted
    
    # Relationships
    organization = relationship("Organization")
    permissions = relationship("OrganizationPermission", secondary=organization_role_permissions, back_populates="roles")

