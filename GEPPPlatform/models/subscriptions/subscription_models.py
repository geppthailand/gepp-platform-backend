"""
Subscription and permission models
"""

from sqlalchemy import (
    Column, String, Text, ForeignKey, BigInteger, Boolean, Integer, JSON, Table,
    DateTime, Numeric,
)
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
    
    name = Column(String(100), nullable=False)  # e.g., 'free', 'starter', 'professional', 'enterprise' — uniqueness enforced via partial index (is_active=true)
    display_name = Column(String(255))
    description = Column(Text)
    price_monthly = Column(Integer, default=0)  # Price in cents
    price_yearly = Column(Integer, default=0)

    # Marks the plan new sign-ups land on. Exactly one row may have
    # ``is_default = TRUE`` at a time (enforced by a partial unique index,
    # see migration 065). The register flow and any other "no plan
    # specified" path should pick the row where this is true — *not*
    # subscription_plan_id = 1 or filter_by(name='free').first(), both of
    # which break when admins create a new plan version.
    is_default = Column(Boolean, nullable=False, default=False)
    
    # Limits
    max_users = Column(Integer, default=1)
    max_transactions_monthly = Column(Integer, default=100)
    max_storage_gb = Column(Integer, default=1)
    max_api_calls_daily = Column(Integer, default=1000)
    
    # Features as JSON
    features = Column(JSON)  # JSON array of feature strings

    # Permission IDs as JSONB array — stores system_permission IDs granted by this plan
    permission_ids = Column(JSON, nullable=False, default=[])

    # Relationships
    subscriptions = relationship("Subscription", back_populates="plan")
    
class Subscription(Base, BaseModel):
    """One SUBSCRIPTION PERIOD for an organization.

    Despite the ``current_period_*`` column names, an org has MANY of these —
    one per contracted period — and `organizations.subscription_id` names the
    one ops considers current. The backoffice `Subscription` tab creates and
    lists them; `services/subscriptions/limits.py` resolves which one covers a
    given date.

    Two limits live here and they behave in opposite ways:

      * ``create_transaction_limit`` — transactions allowed per MONTH. Purely
        advisory: nothing blocks on it, it feeds billing. The period total is
        derived (allowance x months covered), never stored.
      * ``max_file_size_mb`` — enforced. Over-limit uploads are refused.
    """
    __tablename__ = 'subscriptions'

    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    plan_id = Column(BigInteger, ForeignKey('subscription_plans.id'), nullable=False)

    status = Column(String(50), default='active')  # active, suspended, cancelled, expired

    # These three are TIMESTAMPTZ in the schema, not text — migration 063 writes
    # NOW() / NOW() + INTERVAL into them. They were declared String(50) here,
    # which made SQLAlchemy hand back whatever str() it could and silently broke
    # any date comparison done in Python.
    trial_ends_at = Column(DateTime(timezone=True))
    current_period_starts_at = Column(DateTime(timezone=True))
    current_period_ends_at = Column(DateTime(timezone=True))

    # Period metadata (migration 088)
    period_label = Column(String(120))
    notes = Column(Text)
    #: Max size of ONE uploaded file, MB. NULL -> org default -> system default.
    max_file_size_mb = Column(Numeric(8, 2))

    # Usage tracking
    users_count = Column(Integer, default=1)
    transactions_count_this_month = Column(Integer, default=0)
    storage_used_gb = Column(Integer, default=0)
    api_calls_today = Column(Integer, default=0)

    # Transaction and AI audit limits (usage now tracked in subscription_monthly_quotas)
    create_transaction_limit = Column(Integer, default=100)
    ai_audit_limit = Column(Integer, default=10)
    duration_type = Column(String(20), default='monthly')
    allow_ai_audit_exceed_quota = Column(Boolean, default=False)
    
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

