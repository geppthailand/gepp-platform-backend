"""
EPR Payment Transaction models
Handle payment processing for EPR programs
"""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, DateTime, Boolean, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.types import DECIMAL
from ..base import Base, BaseModel

class EprPaymentTransactionType(Base, BaseModel):
    """Types of EPR payment transactions"""
    __tablename__ = 'epr_payment_transaction_types'
    
    # Type identification
    name = Column(String(255), nullable=False)
    code = Column(String(50), unique=True)
    description = Column(Text)
    
    # Category and classification
    category = Column(String(100))  # fee, penalty, refund, incentive
    subcategory = Column(String(100))
    
    # Processing rules
    requires_approval = Column(Boolean, default=False)
    auto_process = Column(Boolean, default=True)
    approval_threshold = Column(DECIMAL(15, 2))  # Amount requiring approval
    
    # Fee calculation
    calculation_method = Column(String(100))  # fixed, percentage, weight_based, volume_based
    base_amount = Column(DECIMAL(10, 2))
    rate_percentage = Column(DECIMAL(5, 2))
    minimum_amount = Column(DECIMAL(10, 2))
    maximum_amount = Column(DECIMAL(10, 2))
    
    # Accounting
    account_code = Column(String(50))
    tax_applicable = Column(Boolean, default=False)
    tax_rate = Column(DECIMAL(5, 2))
    
    # Timing
    payment_due_days = Column(BigInteger, default=30)
    late_penalty_rate = Column(DECIMAL(5, 2))  # Daily penalty percentage
    grace_period_days = Column(BigInteger, default=0)
    
    # Status
    is_active = Column(Boolean, default=True)
    effective_from = Column(DateTime)
    effective_to = Column(DateTime)
    
    # Configuration
    extra_metadata = Column(JSON)  # Flexible configuration options

class EprPaymentTransaction(Base, BaseModel):
    """Main EPR payment transactions"""
    __tablename__ = 'epr_payment_transactions'
    
    # Transaction identification
    transaction_number = Column(String(100), unique=True, nullable=False)
    transaction_type_id = Column(BigInteger, ForeignKey('epr_payment_transaction_types.id'), nullable=False)
    reference_number = Column(String(100))
    
    # Parties involved
    payer_organization_id = Column(BigInteger, ForeignKey('epr_organizations.id'))
    payer_user_id = Column(BigInteger, ForeignKey('user_locations.id'))
    payee_organization_id = Column(BigInteger, ForeignKey('epr_organizations.id'))
    
    # Related entities
    epr_project_id = Column(BigInteger, ForeignKey('epr_project.id'))
    related_transaction_id = Column(BigInteger, ForeignKey('transactions.id'))  # Waste transaction
    
    # Financial details
    gross_amount = Column(DECIMAL(15, 2), nullable=False)
    tax_amount = Column(DECIMAL(15, 2), default=0)
    discount_amount = Column(DECIMAL(15, 2), default=0)
    penalty_amount = Column(DECIMAL(15, 2), default=0)
    net_amount = Column(DECIMAL(15, 2), nullable=False)
    currency = Column(String(3), default='THB')
    
    # Exchange rate (for foreign currencies)
    exchange_rate = Column(DECIMAL(10, 6))
    base_currency_amount = Column(DECIMAL(15, 2))
    
    # Transaction dates
    transaction_date = Column(DateTime, nullable=False)
    due_date = Column(DateTime)
    payment_date = Column(DateTime)
    
    # Status and processing
    status = Column(String(50), default='pending')  # pending, processing, paid, failed, cancelled
    payment_method = Column(String(100))  # bank_transfer, credit_card, cash, check
    payment_reference = Column(String(255))
    
    # Bank/payment details
    bank_account_id = Column(BigInteger)
    payment_gateway = Column(String(100))
    gateway_transaction_id = Column(String(255))
    gateway_response = Column(JSON)
    
    # Processing details
    processed_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    processed_date = Column(DateTime)
    processing_notes = Column(Text)
    
    # Approval workflow
    requires_approval = Column(Boolean, default=False)
    approved_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    approved_date = Column(DateTime)
    approval_notes = Column(Text)
    
    # Reconciliation
    is_reconciled = Column(Boolean, default=False)
    reconciled_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    reconciled_date = Column(DateTime)
    reconciliation_reference = Column(String(255))
    
    # Calculation basis (for fee calculations)
    calculation_data = Column(JSON)  # Weight, volume, rates used
    
    # Additional information
    description = Column(Text)
    internal_notes = Column(Text)
    extra_metadata = Column(JSON)
    
    # Relationships
    transaction_type = relationship("EprPaymentTransactionType")
    payer_organization = relationship("EprOrganization", foreign_keys=[payer_organization_id])
    payer_user = relationship("UserLocation", foreign_keys=[payer_user_id])
    payee_organization = relationship("EprOrganization", foreign_keys=[payee_organization_id])
    epr_project = relationship("EprProject")
    related_transaction = relationship("Transaction")
    
    processed_by = relationship("UserLocation", foreign_keys=[processed_by_id])
    approved_by = relationship("UserLocation", foreign_keys=[approved_by_id])
    reconciled_by = relationship("UserLocation", foreign_keys=[reconciled_by_id])
    
    records = relationship("EprPaymentTransactionRecord", back_populates="payment_transaction")
    images = relationship("EprPaymentTransactionImage", back_populates="payment_transaction")

class EprPaymentTransactionRecord(Base, BaseModel):
    """Detailed records within payment transactions"""
    __tablename__ = 'epr_payment_transaction_records'
    
    payment_transaction_id = Column(BigInteger, ForeignKey('epr_payment_transactions.id'), nullable=False)
    
    # Line item details
    line_number = Column(BigInteger, nullable=False)
    description = Column(Text, nullable=False)
    
    # Material/service details
    material_id = Column(BigInteger, ForeignKey('materials.id'))
    service_type = Column(String(100))
    
    # Quantities
    quantity = Column(DECIMAL(15, 2), nullable=False)
    unit = Column(String(20), default='kg')
    
    # Pricing
    unit_rate = Column(DECIMAL(10, 4), nullable=False)
    line_amount = Column(DECIMAL(15, 2), nullable=False)
    
    # Applicable periods
    period_from = Column(DateTime)
    period_to = Column(DateTime)
    
    # Geographic scope
    province_id = Column(BigInteger, ForeignKey('location_provinces.id'))
    district_id = Column(BigInteger, ForeignKey('location_districts.id'))
    
    # Calculation details
    base_calculation = Column(JSON)  # Detailed calculation breakdown
    adjustments = Column(JSON)  # Any adjustments applied
    
    # Reference data
    reference_transaction_id = Column(BigInteger, ForeignKey('transactions.id'))
    reference_data = Column(JSON)  # Links to source data
    
    # Status
    is_verified = Column(Boolean, default=False)
    verified_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    verified_date = Column(DateTime)
    
    # Notes
    notes = Column(Text)
    
    # Relationships
    payment_transaction = relationship("EprPaymentTransaction", back_populates="records")
    material = relationship("Material")
    province = relationship("LocationProvince")
    district = relationship("LocationDistrict")
    reference_transaction = relationship("Transaction")
    verified_by = relationship("UserLocation")

class EprPaymentTransactionImage(Base, BaseModel):
    """Images/documents attached to payment transactions"""
    __tablename__ = 'epr_payment_transaction_images'
    
    payment_transaction_id = Column(BigInteger, ForeignKey('epr_payment_transactions.id'), nullable=False)
    
    # Image/document details
    image_url = Column(Text, nullable=False)
    thumbnail_url = Column(Text)
    file_name = Column(String(255))
    file_size = Column(BigInteger)  # bytes
    mime_type = Column(String(100))
    
    # Document type and purpose
    document_type = Column(String(100))  # invoice, receipt, proof_of_payment, etc.
    title = Column(String(255))
    description = Column(Text)
    
    # Upload details
    uploaded_by_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    uploaded_date = Column(DateTime, nullable=False)
    
    # Processing status
    is_processed = Column(Boolean, default=False)
    ocr_text = Column(Text)  # Extracted text from OCR
    extracted_data = Column(JSON)  # Structured data extracted
    
    # Verification
    is_verified = Column(Boolean, default=False)
    verified_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    verified_date = Column(DateTime)
    verification_notes = Column(Text)
    
    # Access control
    is_public = Column(Boolean, default=False)
    access_level = Column(String(50), default='transaction_parties')
    
    # Additional metadata
    capture_date = Column(DateTime)
    capture_location = Column(String(255))
    extra_metadata = Column(JSON)  # EXIF, GPS, etc.
    
    # Relationships
    payment_transaction = relationship("EprPaymentTransaction", back_populates="images")
    uploaded_by = relationship("UserLocation", foreign_keys=[uploaded_by_id])
    verified_by = relationship("UserLocation", foreign_keys=[verified_by_id])