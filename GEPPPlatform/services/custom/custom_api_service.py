"""
Custom API Service

Handles organization lookup, API access validation, and quota tracking.
"""

from typing import Optional, Tuple, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from GEPPPlatform.models.subscriptions.organizations import Organization
from GEPPPlatform.models.custom.custom_apis import CustomApi, OrganizationCustomApi
from GEPPPlatform.exceptions import APIException


class CustomApiService:
    """Service for managing custom API access and execution"""
    
    def __init__(self, db_session: Session):
        self.db = db_session
    
    def get_organization_by_api_path(self, api_path: str) -> Optional[Organization]:
        """
        Look up an organization by its api_path.
        
        Args:
            api_path: The unique API path identifier
            
        Returns:
            Organization if found, None otherwise
        """
        return self.db.query(Organization).filter(
            Organization.api_path == api_path,
            Organization.deleted_date.is_(None)
        ).first()
    
    def get_custom_api_by_service_path(self, service_path: str) -> Optional[CustomApi]:
        """
        Look up a custom API by its service path.
        
        Args:
            service_path: The service path (e.g., 'ai_audit/v1')
            
        Returns:
            CustomApi if found, None otherwise
        """
        return self.db.query(CustomApi).filter(
            CustomApi.service_path == service_path,
            CustomApi.deleted_date.is_(None)
        ).first()
    
    def get_organization_api_access(
        self, 
        organization_id: int, 
        custom_api_id: int
    ) -> Optional[OrganizationCustomApi]:
        """
        Get the organization's access configuration for a specific API.
        
        Args:
            organization_id: The organization ID
            custom_api_id: The custom API ID
            
        Returns:
            OrganizationCustomApi if found, None otherwise
        """
        return self.db.query(OrganizationCustomApi).filter(
            OrganizationCustomApi.organization_id == organization_id,
            OrganizationCustomApi.custom_api_id == custom_api_id,
            OrganizationCustomApi.deleted_date.is_(None)
        ).first()
    
    def validate_api_access(
        self, 
        api_path: str, 
        service_path: str
    ) -> Tuple[Organization, CustomApi, OrganizationCustomApi]:
        """
        Validate that an organization has access to a specific API.
        
        Args:
            api_path: The organization's API path
            service_path: The service path being accessed
            
        Returns:
            Tuple of (Organization, CustomApi, OrganizationCustomApi)
            
        Raises:
            APIException: If validation fails
        """
        # 1. Look up organization
        organization = self.get_organization_by_api_path(api_path)
        if not organization:
            raise APIException(
                status_code=404,
                message=f"Organization not found for api_path: {api_path}",
                error_code="ORG_NOT_FOUND"
            )
        
        # 2. Look up custom API
        custom_api = self.get_custom_api_by_service_path(service_path)
        if not custom_api:
            raise APIException(
                status_code=404,
                message=f"API service not found: {service_path}",
                error_code="API_NOT_FOUND"
            )
        
        # 3. Check organization access
        org_api = self.get_organization_api_access(organization.id, custom_api.id)
        if not org_api:
            raise APIException(
                status_code=403,
                message=f"Organization does not have access to this API",
                error_code="API_ACCESS_DENIED"
            )
        
        # 4. Check if enabled
        if not org_api.enable:
            raise APIException(
                status_code=403,
                message="API access is disabled for this organization",
                error_code="API_DISABLED"
            )
        
        # 5. Check expiration
        if org_api.expired_date and org_api.expired_date < datetime.now(timezone.utc):
            raise APIException(
                status_code=403,
                message="API access has expired",
                error_code="API_EXPIRED"
            )
        
        # 6. Check API call quota
        if not org_api.has_api_quota():
            raise APIException(
                status_code=429,
                message="API call quota exceeded",
                error_code="QUOTA_EXCEEDED"
            )
        
        return organization, custom_api, org_api
    
    def record_api_call(self, org_api: OrganizationCustomApi, process_units: int = 0) -> None:
        """
        Record an API call and update quota usage.
        
        Args:
            org_api: The organization API access record
            process_units: Number of processing units consumed (e.g., images processed)
        """
        org_api.increment_api_call()
        if process_units > 0:
            org_api.increment_process_usage(process_units)
        self.db.commit()
    
    def get_quota_status(self, org_api: OrganizationCustomApi, require_quota_for_this_call: int = None) -> Dict[str, Any]:
        """
        Get current quota status for an organization's API access.

        Args:
            org_api: The organization API access record
            require_quota_for_this_call: Optional number of process units required for current call

        Returns:
            Dict with quota information
        """
        process_units = {
            "used": org_api.process_used or 0,
            "quota": org_api.process_quota,
            "remaining": (org_api.process_quota or 0) - (org_api.process_used or 0) if org_api.process_quota else None
        }

        # Add require_quota_for_this_call if provided
        if require_quota_for_this_call is not None:
            process_units["require_quota_for_this_call"] = require_quota_for_this_call

        return {
            "api_calls": {
                "used": org_api.api_call_used or 0,
                "quota": org_api.api_call_quota,
                "remaining": (org_api.api_call_quota or 0) - (org_api.api_call_used or 0) if org_api.api_call_quota else None
            },
            "process_units": process_units,
            "expired_date": org_api.expired_date.isoformat() if org_api.expired_date else None,
            "is_valid": org_api.is_valid()
        }
