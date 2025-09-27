"""
GRI Analytics and Export models
Analytics capabilities, dashboards, and export functionality
"""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, DateTime, Boolean, JSON, Enum as SQLEnum
from sqlalchemy.types import DECIMAL
from sqlalchemy.orm import relationship
import enum
from ..base import Base, BaseModel
from .standards import GriStandardType

class ExportFormat(enum.Enum):
    """Export format types"""
    EXCEL = 'excel'
    PDF = 'pdf'
    CSV = 'csv'
    JSON = 'json'
    XML = 'xml'
    API = 'api'

class ChartType(enum.Enum):
    """Chart visualization types"""
    LINE = 'line'
    BAR = 'bar'
    PIE = 'pie'
    DONUT = 'donut'
    GAUGE = 'gauge'
    HEATMAP = 'heatmap'
    TREEMAP = 'treemap'
    SANKEY = 'sankey'
    SCATTER = 'scatter'
    AREA = 'area'

class GriAnalytics(Base, BaseModel):
    """Analytics and insights for GRI data"""
    __tablename__ = 'gri_analytics'
    
    # Analytics identification
    name = Column(String(255), nullable=False)
    code = Column(String(50), unique=True)
    gri_type = Column(SQLEnum(GriStandardType))  # Can be null for cross-standard analytics
    
    # Scope
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    user_location_ids = Column(JSON)  # Array of location IDs
    
    # Time range
    date_from = Column(DateTime, nullable=False)
    date_to = Column(DateTime, nullable=False)
    comparison_period = Column(String(50))  # previous_period, previous_year, baseline
    
    # Metrics configuration
    primary_metric = Column(String(255))
    secondary_metrics = Column(JSON)  # Array of additional metrics
    aggregation_method = Column(String(50))  # sum, average, median, etc.
    grouping_dimensions = Column(JSON)  # Group by: location, material, time
    
    # Calculated insights
    total_waste_analyzed = Column(DECIMAL(15, 2))
    average_monthly_waste = Column(DECIMAL(15, 2))
    peak_waste_period = Column(String(50))
    lowest_waste_period = Column(String(50))
    
    # Trend analysis
    trend_direction = Column(String(20))  # increasing, decreasing, stable
    trend_percentage = Column(DECIMAL(5, 2))
    forecast_next_period = Column(DECIMAL(15, 2))
    confidence_interval = Column(JSON)  # {lower: x, upper: y}
    
    # Performance metrics
    goal_achievement_rate = Column(DECIMAL(5, 2))
    benchmark_comparison = Column(JSON)  # Comparison with industry benchmarks
    percentile_ranking = Column(DECIMAL(5, 2))  # Industry percentile
    
    # Key findings
    key_insights = Column(JSON)  # Array of insight objects
    recommendations = Column(JSON)  # Array of recommendations
    risk_factors = Column(JSON)  # Identified risks
    opportunities = Column(JSON)  # Improvement opportunities
    
    # Visualization configuration
    default_chart_type = Column(SQLEnum(ChartType))
    chart_configurations = Column(JSON)  # Chart-specific settings
    color_scheme = Column(JSON)  # Color configurations
    
    # Filters applied
    filters = Column(JSON)  # Active filters for this analytics
    
    # Caching
    is_cached = Column(Boolean, default=False)
    cache_updated = Column(DateTime)
    cache_expiry = Column(DateTime)
    
    # Usage tracking
    view_count = Column(BigInteger, default=0)
    last_viewed = Column(DateTime)
    
    # Sharing and access
    is_public = Column(Boolean, default=False)
    shared_with = Column(JSON)  # Array of user IDs
    
    # Relationships
    organization = relationship("Organization")
    dashboard_widgets = relationship("GriDashboardWidget", back_populates="analytics")

class GriDashboard(Base, BaseModel):
    """Dashboard configurations for GRI reporting"""
    __tablename__ = 'gri_dashboards'
    
    # Dashboard identification
    name = Column(String(255), nullable=False)
    code = Column(String(50), unique=True)
    description = Column(Text)
    
    # Ownership and access
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    owner_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    
    # Dashboard type
    dashboard_type = Column(String(50))  # executive, operational, compliance
    gri_types = Column(JSON)  # Array of GRI types covered
    
    # Layout configuration
    layout = Column(JSON)  # Grid layout configuration
    theme = Column(String(50))  # Dashboard theme
    
    # Default settings
    default_date_range = Column(String(50))  # last_month, last_quarter, ytd
    default_locations = Column(JSON)  # Default location filters
    auto_refresh = Column(Boolean, default=False)
    refresh_interval = Column(BigInteger)  # Minutes
    
    # Sharing and permissions
    is_public = Column(Boolean, default=False)
    is_default = Column(Boolean, default=False)  # Default dashboard for org
    shared_users = Column(JSON)  # Array of user IDs with access
    permission_level = Column(String(50))  # view, edit, admin
    
    # Usage tracking
    view_count = Column(BigInteger, default=0)
    last_accessed = Column(DateTime)
    
    # Status
    is_active = Column(Boolean, default=True)
    
    # Version control
    version = Column(String(20), default='1.0')
    
    # Relationships
    organization = relationship("Organization")
    owner = relationship("UserLocation")
    widgets = relationship("GriDashboardWidget", back_populates="dashboard")

class GriDashboardWidget(Base, BaseModel):
    """Individual widgets within GRI dashboards"""
    __tablename__ = 'gri_dashboard_widgets'
    
    dashboard_id = Column(BigInteger, ForeignKey('gri_dashboards.id'), nullable=False)
    analytics_id = Column(BigInteger, ForeignKey('gri_analytics.id'))
    
    # Widget configuration
    widget_type = Column(String(50))  # chart, metric, table, text
    title = Column(String(255))
    subtitle = Column(String(500))
    
    # Position and size
    position_x = Column(BigInteger)
    position_y = Column(BigInteger)
    width = Column(BigInteger)
    height = Column(BigInteger)
    
    # Visualization
    chart_type = Column(SQLEnum(ChartType))
    chart_config = Column(JSON)  # Chart-specific configuration
    
    # Data configuration
    data_source = Column(String(100))  # analytics, direct_query, static
    query_config = Column(JSON)  # Query configuration if direct
    static_data = Column(JSON)  # Static data if applicable
    
    # Display settings
    show_legend = Column(Boolean, default=True)
    show_labels = Column(Boolean, default=True)
    decimal_places = Column(BigInteger, default=2)
    
    # Interactivity
    is_interactive = Column(Boolean, default=True)
    drill_down_enabled = Column(Boolean, default=False)
    linked_widgets = Column(JSON)  # IDs of linked widgets
    
    # Refresh settings
    auto_refresh = Column(Boolean)
    refresh_interval = Column(BigInteger)  # Seconds
    
    # Status
    is_visible = Column(Boolean, default=True)
    sort_order = Column(BigInteger, default=0)
    
    # Relationships
    dashboard = relationship("GriDashboard", back_populates="widgets")
    analytics = relationship("GriAnalytics", back_populates="dashboard_widgets")

class GriExport(Base, BaseModel):
    """Export configurations and history for GRI reports"""
    __tablename__ = 'gri_exports'
    
    # Export identification
    export_id = Column(String(100), unique=True, nullable=False)
    name = Column(String(255))
    
    # Source configuration
    export_type = Column(String(50))  # report, analytics, dashboard, custom
    source_reports = Column(JSON)  # Array of report IDs
    source_analytics = Column(JSON)  # Array of analytics IDs
    
    # Format and output
    export_format = Column(SQLEnum(ExportFormat), nullable=False)
    file_name = Column(String(255))
    file_path = Column(Text)
    file_size = Column(BigInteger)  # bytes
    
    # Content configuration
    include_sections = Column(JSON)  # Sections to include
    exclude_sections = Column(JSON)  # Sections to exclude
    
    # Formatting options
    template_id = Column(BigInteger, ForeignKey('gri_export_templates.id'))
    custom_formatting = Column(JSON)  # Custom format settings
    include_charts = Column(Boolean, default=True)
    include_tables = Column(Boolean, default=True)
    include_appendix = Column(Boolean, default=False)
    
    # Data filters
    date_range_from = Column(DateTime)
    date_range_to = Column(DateTime)
    location_filters = Column(JSON)
    material_filters = Column(JSON)
    
    # Processing
    status = Column(String(50), default='pending')  # pending, processing, completed, failed
    processing_started = Column(DateTime)
    processing_completed = Column(DateTime)
    error_message = Column(Text)
    
    # Delivery
    delivery_method = Column(String(50))  # download, email, api, storage
    delivery_emails = Column(JSON)  # Email addresses
    delivery_url = Column(Text)  # Download URL
    
    # Access control
    is_public = Column(Boolean, default=False)
    expiry_date = Column(DateTime)
    password_protected = Column(Boolean, default=False)
    
    # Metadata
    generated_by_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    generated_date = Column(DateTime, nullable=False)
    
    # Usage tracking
    download_count = Column(BigInteger, default=0)
    last_accessed = Column(DateTime)
    
    # Relationships
    generated_by = relationship("UserLocation")
    template = relationship("GriExportTemplate")

class GriExportTemplate(Base, BaseModel):
    """Templates for GRI report exports"""
    __tablename__ = 'gri_export_templates'
    
    # Template identification
    name = Column(String(255), nullable=False)
    code = Column(String(50), unique=True)
    description = Column(Text)
    
    # Template type
    template_type = Column(String(50))  # standard, regulatory, custom
    export_format = Column(SQLEnum(ExportFormat), nullable=False)
    
    # Template content
    template_file = Column(Text)  # Template file path
    template_structure = Column(JSON)  # JSON structure
    
    # Sections and components
    header_config = Column(JSON)
    footer_config = Column(JSON)
    section_configs = Column(JSON)  # Configuration for each section
    
    # Styling
    style_sheet = Column(Text)  # CSS or styling rules
    color_scheme = Column(JSON)
    font_settings = Column(JSON)
    
    # Data mapping
    field_mappings = Column(JSON)  # Map data fields to template
    calculation_rules = Column(JSON)  # Calculations to perform
    
    # Charts and visuals
    chart_templates = Column(JSON)  # Chart configurations
    image_placeholders = Column(JSON)  # Image positions
    
    # Compliance and standards
    compliance_standard = Column(String(100))  # GRI, SASB, TCFD, etc.
    regulatory_requirements = Column(JSON)
    
    # Localization
    supported_languages = Column(JSON)  # Array of language codes
    default_language = Column(String(10), default='en')
    
    # Version control
    version = Column(String(20), default='1.0')
    is_default = Column(Boolean, default=False)
    
    # Usage
    times_used = Column(BigInteger, default=0)
    last_used = Column(DateTime)
    
    # Status
    is_active = Column(Boolean, default=True)
    created_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    
    # Relationships
    created_by = relationship("UserLocation")

class GriDataConnector(Base, BaseModel):
    """Data connectors for external systems integration"""
    __tablename__ = 'gri_data_connectors'
    
    # Connector identification
    name = Column(String(255), nullable=False)
    code = Column(String(50), unique=True)
    connector_type = Column(String(100))  # database, api, file, iot
    
    # Connection details
    connection_string = Column(Text)  # Encrypted
    api_endpoint = Column(Text)
    authentication_method = Column(String(50))  # api_key, oauth, basic
    credentials = Column(JSON)  # Encrypted credentials
    
    # Data mapping
    source_schema = Column(JSON)  # Source data structure
    field_mappings = Column(JSON)  # Map source to GRI fields
    transformation_rules = Column(JSON)  # Data transformation rules
    
    # Sync configuration
    sync_frequency = Column(String(50))  # real_time, hourly, daily, weekly
    last_sync = Column(DateTime)
    next_sync = Column(DateTime)
    
    # Data filters
    source_filters = Column(JSON)  # Filters to apply at source
    
    # Error handling
    error_threshold = Column(BigInteger, default=10)
    retry_attempts = Column(BigInteger, default=3)
    last_error = Column(Text)
    error_count = Column(BigInteger, default=0)
    
    # Performance
    average_sync_duration = Column(BigInteger)  # Seconds
    records_per_sync = Column(BigInteger)
    
    # Status
    is_active = Column(Boolean, default=True)
    is_healthy = Column(Boolean, default=True)
    
    # Organization
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    
    # Relationships
    organization = relationship("Organization")