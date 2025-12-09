"""
Reports module for GEPP Platform
Handles report generation and analytics
"""

# Avoid importing heavy dependencies (like SQLAlchemy) at package import time.
try:
    from .reports_handlers import handle_reports_routes  # noqa: F401
    from .reports_service import ReportsService  # noqa: F401
    __all__ = ['handle_reports_routes', 'ReportsService']
except Exception:
    __all__ = []

