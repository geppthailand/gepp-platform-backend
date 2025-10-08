"""
Reports module for GEPP Platform
Handles report generation and analytics
"""

from .reports_handlers import handle_reports_routes
from .reports_service import ReportsService

__all__ = ['handle_reports_routes', 'ReportsService']

