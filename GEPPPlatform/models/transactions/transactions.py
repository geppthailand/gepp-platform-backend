"""
Transactions - Grouped shipment batches of transaction records
Represents a collection of materials moving together from one location to another
"""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, DateTime, Boolean, Enum, CheckConstraint, func, event
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.types import DECIMAL
import enum
from datetime import datetime
from ..base import Base, BaseModel

class TransactionStatus(enum.Enum):
    draft = 'draft'
    pending = 'pending'
    scheduled = 'scheduled'
    approved = 'approved'
    in_progress = 'in_progress'
    in_transit = 'in_transit'
    delivered = 'delivered'
    completed = 'completed'
    cancelled = 'cancelled'
    rejected = 'rejected'

class TransactionRecordStatus(enum.Enum):
    draft = 'draft'
    pending = 'pending'
    in_progress = 'in_progress'
    completed = 'completed'
    rejected = 'rejected'
    cancelled = 'cancelled'

class TransactionPriority(enum.Enum):
    LOW = 'low'
    NORMAL = 'normal'
    HIGH = 'high'
    URGENT = 'urgent'

class AIAuditStatus(enum.Enum):
    null = 'null'  # Not yet queued for audit (mimics NULL)
    queued = 'queued'  # Queued for AI audit
    approved = 'approved'
    rejected = 'rejected'
    no_action = 'no_action'

class Transaction(Base, BaseModel):
    """
    Main transaction table - represents a batch/shipment of materials
    Restructured to focus on logistics and batch management
    """
    __tablename__ = 'transactions'

    # Transaction records management
    transaction_records = Column(ARRAY(BigInteger), nullable=False, default=[])  # Array of transaction_record IDs

    # Transaction method
    transaction_method = Column(String(50), nullable=False, default='origin')  # origin, transport, transform

    # Status
    status = Column(Enum(TransactionStatus), default=TransactionStatus.pending)

    # AI Audit Status - separate from actual status
    ai_audit_status = Column(Enum(AIAuditStatus), nullable=False, default=AIAuditStatus.null)
    ai_audit_note = Column(Text, nullable=True)  # Stores full audit response JSONB as text
    reject_triggers = Column(JSONB, nullable=False, default=[])  # Array of rule_ids that triggered rejection
    warning_triggers = Column(JSONB, nullable=False, default=[])  # Array of rule_ids that triggered warnings

    # User Audit Status - tracks if transaction was manually audited by user
    is_user_audit = Column(Boolean, nullable=False, default=False)

    # Organization and locations
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=True)
    origin_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=True)
    destination_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=True)
    location_tag_id = Column(BigInteger, nullable=True)
    ext_id_1 = Column(String(50), nullable=True)
    ext_id_2 = Column(String(50), nullable=True)

    # Aggregated data
    weight_kg = Column(DECIMAL(15, 4), nullable=False, default=0)
    total_amount = Column(DECIMAL(15, 4), nullable=False, default=0)

    # Date tracking
    transaction_date = Column(DateTime, nullable=False, default=func.now())
    arrival_date = Column(DateTime)

    # Location coordinates
    origin_coordinates = Column(JSONB)  # {lat: float, lng: float}
    destination_coordinates = Column(JSONB)  # {lat: float, lng: float}

    # Documentation and notes
    notes = Column(Text)
    images = Column(JSONB, nullable=False, default=[])  # Array of image URLs/paths

    # Vehicle and driver information
    vehicle_info = Column(JSONB)  # {license, type, capacity, etc.}
    driver_info = Column(JSONB)  # {name, license, contact, etc.}

    # Hazardous and treatment information
    hazardous_level = Column(BigInteger, nullable=False, default=0)  # 0-5 scale
    treatment_method = Column(String(255))
    disposal_method = Column(String(255))

    # People involved
    created_by_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=True)
    updated_by_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=True)
    approved_by_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=True)

    # Constraints
    __table_args__ = (
        CheckConstraint('transaction_method IN (\'origin\', \'transport\', \'transform\')', name='chk_transaction_method'),
        CheckConstraint('hazardous_level BETWEEN 0 AND 5', name='chk_hazardous_level'),
        CheckConstraint('weight_kg >= 0', name='chk_weight_kg'),
        CheckConstraint('total_amount >= 0', name='chk_total_amount'),
    )

    # Relationships
    organization = relationship("Organization")
    origin = relationship("UserLocation", foreign_keys=[origin_id])
    destination = relationship("UserLocation", foreign_keys=[destination_id])
    created_by = relationship("UserLocation", foreign_keys=[created_by_id])
    updated_by = relationship("UserLocation", foreign_keys=[updated_by_id])
    approved_by = relationship("UserLocation", foreign_keys=[approved_by_id])
    # Note: Using JSONB fields for images instead of relationships to avoid table dependencies
    
    def calculate_totals(self):
        """Calculate total weight, volume, and value from transaction records"""
        if self.records:
            self.total_weight = sum(r.quantity for r in self.records if r.unit in ['kg', 'ton'])
            self.total_volume = sum(r.volume for r in self.records if r.volume)
            self.total_items = len(self.records)
            self.total_value = sum(r.total_value for r in self.records if r.total_value)
        return self.total_weight, self.total_volume, self.total_items, self.total_value
    
    def update_status(self, new_status):
        """Update transaction status and relevant timestamps"""
        self.status = new_status
        
        if new_status == TransactionStatus.in_transit:
            self.actual_pickup_date = datetime.now()
        elif new_status == TransactionStatus.delivered:
            self.actual_delivery_date = datetime.now()
        elif new_status == TransactionStatus.completed:
            self.completed_date = datetime.now()
    
    def is_complete(self):
        """Check if all records in transaction are completed"""
        if not self.records:
            return False
        return all(r.completion_date is not None for r in self.records)

    # def auto_transition_to_pending(self):
    #     """Automatically transition from DRAFT to PENDING when transaction has required data"""
    #     if (self.status == TransactionStatus.pending and
    #         self.has_minimum_required_data()):
    #         self.status = TransactionStatus.pending
    #         return True
    #     return False

    def has_minimum_required_data(self):
        """Check if transaction has minimum required data to move from DRAFT to PENDING"""
        return (
            self.transaction_records and  # Has at least one transaction record
            len(self.transaction_records) > 0 and
            self.origin_id is not None and  # Has origin location
            self.organization_id is not None  # Belongs to an organization
        )


# # Event listeners for automatic status transitions
# @event.listens_for(Transaction, 'before_insert')
# def auto_set_pending_on_insert(_mapper, _connection, target):
#     """Automatically set status to PENDING if transaction has required data on creation"""
#     if target.status == TransactionStatus.DRAFT:
#         target.auto_transition_to_pending()


# @event.listens_for(Transaction, 'before_update')
# def auto_set_pending_on_update(_mapper, _connection, target):
#     """Automatically set status to PENDING if transaction gets required data on update"""
#     if target.status == TransactionStatus.DRAFT:
#         target.auto_transition_to_pending()