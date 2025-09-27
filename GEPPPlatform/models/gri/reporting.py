"""
GRI Reporting and Data models
Unified reporting model for GRI 306-1, 306-2, 306-3 standards
"""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, DateTime, Boolean, JSON, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.types import DECIMAL
from ..base import Base, BaseModel
from .standards import GriStandardType
import enum

class ReportingPeriod(enum.Enum):
    """Reporting period types"""
    MONTHLY = 'monthly'
    QUARTERLY = 'quarterly'
    SEMI_ANNUAL = 'semi_annual'
    ANNUAL = 'annual'
    CUSTOM = 'custom'

class GriReport(Base, BaseModel):
    """
    Unified GRI reporting table for all GRI 306 standards
    Single table design with gri_type classification
    """
    __tablename__ = 'gri_reports'
    
    # Report identification
    report_id = Column(String(100), unique=True, nullable=False)
    gri_type = Column(SQLEnum(GriStandardType), nullable=False)  # 306-1, 306-2, 306-3
    
    # Organization and scope
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    user_location_id = Column(BigInteger, ForeignKey('user_locations.id'))  # Specific facility
    
    # Reporting period
    reporting_period = Column(SQLEnum(ReportingPeriod), nullable=False)
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    year = Column(BigInteger, nullable=False)
    quarter = Column(BigInteger)  # 1-4
    month = Column(BigInteger)  # 1-12
    
    # === GRI 306-1: Waste Generation and Impacts ===
    # Stored when gri_type = GRI_306_1
    waste_sources = Column(JSON)  # {source: description} mapping
    upstream_impacts = Column(JSON)  # Upstream value chain impacts
    downstream_impacts = Column(JSON)  # Downstream impacts
    significant_impacts = Column(JSON)  # List of significant impacts
    impact_assessment_method = Column(Text)
    
    # === GRI 306-2: Management of Impacts ===
    # Stored when gri_type = GRI_306_2
    prevention_actions = Column(JSON)  # Waste prevention initiatives
    circularity_measures = Column(JSON)  # Circular economy measures
    management_processes = Column(JSON)  # Management process descriptions
    stakeholder_engagement = Column(JSON)  # Stakeholder involvement
    effectiveness_metrics = Column(JSON)  # Effectiveness measurements
    
    # === GRI 306-3: Waste Generated ===
    # Stored when gri_type = GRI_306_3
    waste_generated_total = Column(DECIMAL(15, 2))  # Total waste in tonnes
    hazardous_waste = Column(DECIMAL(15, 2))
    non_hazardous_waste = Column(DECIMAL(15, 2))
    
    # Waste composition breakdown
    waste_by_material = Column(JSON)  # {material: amount} in tonnes
    waste_by_source = Column(JSON)  # {source: amount} breakdown
    waste_by_location = Column(JSON)  # {location: amount} breakdown
    
    # Additional metrics for 306-3
    recycled_waste = Column(DECIMAL(15, 2))
    landfilled_waste = Column(DECIMAL(15, 2))
    incinerated_waste = Column(DECIMAL(15, 2))
    composted_waste = Column(DECIMAL(15, 2))
    other_disposal = Column(DECIMAL(15, 2))
    
    # === Common fields across all GRI types ===
    
    # Flexible metrics storage (JSON for extensibility)
    metrics_data = Column(JSON)  # Flexible field for any additional metrics
    
    # Calculations and derived metrics
    recycling_rate = Column(DECIMAL(5, 2))  # Percentage
    diversion_rate = Column(DECIMAL(5, 2))  # Diversion from landfill %
    reduction_from_baseline = Column(DECIMAL(5, 2))  # % reduction
    
    # Data quality and verification
    data_quality_score = Column(DECIMAL(3, 2))  # 1-5 scale
    data_completeness = Column(DECIMAL(5, 2))  # Percentage
    third_party_verified = Column(Boolean, default=False)
    verification_date = Column(DateTime)
    verifier_name = Column(String(255))
    verification_certificate_url = Column(Text)
    
    # Comparison data
    previous_period_value = Column(DECIMAL(15, 2))
    year_over_year_change = Column(DECIMAL(5, 2))  # Percentage
    baseline_year = Column(BigInteger)
    baseline_value = Column(DECIMAL(15, 2))
    
    # Notes and documentation
    methodology_notes = Column(Text)
    assumptions = Column(Text)
    limitations = Column(Text)
    improvement_actions = Column(JSON)  # Planned improvements
    
    # Supporting documents
    supporting_documents = Column(JSON)  # Array of document references
    evidence_files = Column(JSON)  # Evidence file URLs
    
    # Status and workflow
    status = Column(String(50), default='draft')  # draft, submitted, approved, published
    submitted_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    submitted_date = Column(DateTime)
    approved_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    approved_date = Column(DateTime)
    published_date = Column(DateTime)
    
    # Compliance and certification
    compliance_status = Column(String(50))  # compliant, non_compliant, partial
    compliance_notes = Column(Text)
    certification_status = Column(String(50))
    
    # Metadata
    tags = Column(JSON)  # Array of tags for categorization
    custom_fields = Column(JSON)  # Organization-specific fields
    
    # Relationships
    organization = relationship("Organization")
    user_location = relationship("UserLocation", foreign_keys=[user_location_id])
    submitted_by = relationship("UserLocation", foreign_keys=[submitted_by_id])
    approved_by = relationship("UserLocation", foreign_keys=[approved_by_id])
    
    # Detailed data records
    data_records = relationship("GriReportData", back_populates="report")
    
    def calculate_metrics(self):
        """Calculate derived metrics based on raw data"""
        if self.gri_type == GriStandardType.GRI_306_3:
            if self.waste_generated_total and self.recycled_waste:
                self.recycling_rate = (self.recycled_waste / self.waste_generated_total) * 100
            
            if self.waste_generated_total and self.landfilled_waste:
                self.diversion_rate = ((self.waste_generated_total - self.landfilled_waste) / 
                                      self.waste_generated_total) * 100
        
        # Calculate year-over-year change
        if self.previous_period_value and self.waste_generated_total:
            self.year_over_year_change = ((self.waste_generated_total - self.previous_period_value) / 
                                         self.previous_period_value) * 100

class GriReportData(Base, BaseModel):
    """Detailed data records for GRI reports"""
    __tablename__ = 'gri_report_data'
    
    report_id = Column(BigInteger, ForeignKey('gri_reports.id'), nullable=False)
    
    # Data point identification
    data_category = Column(String(100))  # waste_stream, impact, action, etc.
    data_subcategory = Column(String(100))
    
    # Material or item details
    material_id = Column(BigInteger, ForeignKey('materials.id'))
    material_category_id = Column(BigInteger, ForeignKey('gri_material_categories.id'))
    item_description = Column(String(500))
    
    # Measurements
    quantity = Column(DECIMAL(15, 3))
    unit = Column(String(20))  # kg, tonnes, m3, etc.
    
    # Location and source
    source_location_id = Column(BigInteger, ForeignKey('user_locations.id'))
    source_type = Column(String(100))  # production, office, warehouse, etc.
    
    # Time period specific to this data point
    data_date = Column(DateTime)
    
    # Quality and verification
    data_source = Column(String(255))  # System, manual, estimated
    confidence_level = Column(String(50))  # high, medium, low
    is_estimated = Column(Boolean, default=False)
    estimation_method = Column(Text)
    
    # Supporting information
    notes = Column(Text)
    evidence_url = Column(Text)
    
    # Relationships
    report = relationship("GriReport", back_populates="data_records")
    material = relationship("Material")
    material_category = relationship("GriMaterialCategory")
    source_location = relationship("UserLocation")

class GriReportSnapshot(Base, BaseModel):
    """Point-in-time snapshots of GRI reports for historical tracking"""
    __tablename__ = 'gri_report_snapshots'
    
    report_id = Column(BigInteger, ForeignKey('gri_reports.id'), nullable=False)
    
    # Snapshot details
    snapshot_date = Column(DateTime, nullable=False)
    snapshot_type = Column(String(50))  # manual, auto, submission, approval
    version_number = Column(String(20))
    
    # Complete report data at time of snapshot
    report_data = Column(JSON)  # Complete JSON representation
    
    # Snapshot metadata
    created_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    reason = Column(Text)
    is_milestone = Column(Boolean, default=False)  # Mark important snapshots
    
    # Relationships
    report = relationship("GriReport")
    created_by = relationship("UserLocation")

import enum  # Add this import at the top