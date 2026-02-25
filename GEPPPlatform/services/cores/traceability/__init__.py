"""
Traceability Service Module

This module provides traceability-related API capabilities.
"""

from .traceability_service import TraceabilityService
from .traceability_handlers import handle_traceability_routes

__all__ = ['TraceabilityService', 'handle_traceability_routes']
