"""
Transaction Records - Individual material journey tracking
Each record represents a single material's movement in the waste management system
"""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, DateTime, Boolean, CheckConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.types import DECIMAL
from ..base import Base, BaseModel

class TransactionRecord(Base, BaseModel):
    """
    Represents individual material journey from source to destination
    New restructured version with comprehensive tracking
    """
    __tablename__ = 'transaction_records'

    # Status and basic info
    status = Column(String(50), nullable=False, default='pending')
    created_transaction_id = Column(BigInteger, ForeignKey('transactions.id'), nullable=False)
    traceability = Column(ARRAY(BigInteger), nullable=False, default=[])  # Array of transaction_ids sorted

    # Transaction type
    transaction_type = Column(String(50), nullable=False)  # manual_input, rewards, iot

    # Material identification
    material_id = Column(BigInteger, ForeignKey('materials.id'), nullable=True)
    main_material_id = Column(BigInteger, ForeignKey('main_materials.id'), nullable=False)
    category_id = Column(BigInteger, ForeignKey('material_categories.id'), nullable=False)
    tags = Column(JSONB, nullable=False, default=[])  # Material tag conditions [(tag_group_id, tag_id), ...]

    # Quantity and measurements
    unit = Column(String(100), nullable=False)
    origin_quantity = Column(DECIMAL(15, 4), nullable=False, default=0)
    origin_weight_kg = Column(DECIMAL(15, 4), nullable=False, default=0)
    origin_price_per_unit = Column(DECIMAL(15, 4), nullable=False, default=0)
    total_amount = Column(DECIMAL(15, 4), nullable=False, default=0)
    currency_id = Column(BigInteger, ForeignKey('currencies.id'), nullable=True)

    # Documentation and tracking
    notes = Column(Text)
    images = Column(JSONB, nullable=False, default=[])  # Array of image URLs/paths

    # Location tracking
    origin_coordinates = Column(JSONB)  # {lat: float, lng: float}
    destination_coordinates = Column(JSONB)  # {lat: float, lng: float}

    # Hazardous and treatment information
    hazardous_level = Column(BigInteger, nullable=False, default=0)  # 0-5 scale
    treatment_method = Column(String(255))
    disposal_method = Column(String(255))

    # People involved
    created_by_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    approved_by_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=True)

    # Date tracking
    transaction_date = Column(DateTime)  # Specific transaction date (can differ from created_date)
    completed_date = Column(DateTime)

    # Constraints
    __table_args__ = (
        CheckConstraint('transaction_type IN (\'manual_input\', \'rewards\', \'iot\')', name='chk_transaction_type'),
        CheckConstraint('hazardous_level BETWEEN 0 AND 5', name='chk_hazardous_level'),
        CheckConstraint('origin_quantity >= 0', name='chk_origin_quantity'),
        CheckConstraint('origin_weight_kg >= 0', name='chk_origin_weight_kg'),
        CheckConstraint('origin_price_per_unit >= 0', name='chk_origin_price_per_unit'),
        CheckConstraint('total_amount >= 0', name='chk_total_amount'),
    )

    # Relationships
    created_transaction = relationship("Transaction", foreign_keys=[created_transaction_id])
    material = relationship("Material")
    main_material = relationship("MainMaterial")
    category = relationship("MaterialCategory")
    currency = relationship("Currency")
    created_by = relationship("UserLocation", foreign_keys=[created_by_id])
    approved_by = relationship("UserLocation", foreign_keys=[approved_by_id])
    # Note: Using JSONB 'images' field for storing S3 URLs instead of relationship
    def calculate_total_value(self):
        """Calculate total value based on quantity and unit price"""
        if self.origin_quantity and self.origin_price_per_unit:
            self.total_amount = self.origin_quantity * self.origin_price_per_unit
        return self.total_amount