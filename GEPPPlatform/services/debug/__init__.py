"""
Debug services for development and testing
WARNING: These services should only be available in development environments
"""

from .debug_handlers import handle_debug_routes

__all__ = ['handle_debug_routes']