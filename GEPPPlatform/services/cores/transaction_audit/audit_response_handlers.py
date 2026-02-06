"""
AI Audit Response Pattern API handlers
Manages CRUD operations for AI audit response message templates
"""

from typing import Dict, Any
import logging
import traceback
from sqlalchemy import and_

from ....models.ai_audit_models import AiAuditResponsePattern
from ....exceptions import (
    APIException,
    UnauthorizedException,
    NotFoundException,
    BadRequestException,
    ValidationException
)

logger = logging.getLogger(__name__)


def handle_audit_response_routes(event: Dict[str, Any], data: Dict[str, Any], **params) -> Dict[str, Any]:
    """
    Main handler for audit response pattern routes

    Routes:
    - GET    /api/transaction_audit/responses - List all patterns for organization
    - POST   /api/transaction_audit/responses - Create new pattern
    - GET    /api/transaction_audit/responses/{id} - Get single pattern
    - PUT    /api/transaction_audit/responses/{id} - Update pattern
    - DELETE /api/transaction_audit/responses/{id} - Delete pattern
    """
    path = event.get("rawPath", "")
    method = params.get('method', 'GET')
    query_params = params.get('query_params', {})
    path_params = params.get('path_params', {})

    # Get database session
    db_session = params.get('db_session')
    if not db_session:
        raise APIException('Database session not provided')

    # Get current user info
    current_user = params.get('current_user', {})
    current_user_organization_id = current_user.get('organization_id')

    if not current_user_organization_id:
        raise UnauthorizedException('Organization ID not found in token')

    try:
        # Route to specific handlers
        if path == '/api/transaction_audit/responses':
            if method == 'GET':
                return handle_list_response_patterns(
                    db_session,
                    query_params,
                    current_user_organization_id
                )
            elif method == 'POST':
                return handle_create_response_pattern(
                    db_session,
                    data,
                    current_user_organization_id
                )

        elif path.startswith('/api/transaction_audit/responses/'):
            # Extract pattern ID from path
            # Path format: /api/transaction_audit/responses/{id}
            path_parts = path.rstrip('/').split('/')
            pattern_id_str = path_parts[-1] if len(path_parts) > 0 else None

            if not pattern_id_str or pattern_id_str == 'responses':
                raise NotFoundException('Pattern ID not provided')

            try:
                pattern_id = int(pattern_id_str)
            except ValueError:
                raise BadRequestException('Invalid pattern ID')

            if method == 'GET':
                return handle_get_response_pattern(
                    db_session,
                    pattern_id,
                    current_user_organization_id
                )
            elif method == 'PUT':
                return handle_update_response_pattern(
                    db_session,
                    pattern_id,
                    data,
                    current_user_organization_id
                )
            elif method == 'DELETE':
                return handle_delete_response_pattern(
                    db_session,
                    pattern_id,
                    current_user_organization_id
                )

        raise NotFoundException(f'Audit response route not found: {method} {path}')

    except APIException:
        raise
    except Exception as e:
        logger.error(f'Unexpected error in audit response handler: {str(e)}')
        logger.error(f'Traceback: {traceback.format_exc()}')
        raise APIException(f'Internal server error: {str(e)}')


def handle_list_response_patterns(
    db_session: Any,
    query_params: Dict[str, Any],
    organization_id: int
) -> Dict[str, Any]:
    """
    GET /api/transaction_audit/responses
    List all response patterns for the organization

    Query params:
    - code: str (optional) - Filter by specific code
    """
    try:
        logger.info(f"Listing response patterns for organization {organization_id}")

        # Build query
        query = db_session.query(AiAuditResponsePattern).filter(
            and_(
                AiAuditResponsePattern.organization_id == organization_id,
                AiAuditResponsePattern.is_active == True,
                AiAuditResponsePattern.deleted_date.is_(None)
            )
        )

        # Apply code filter if provided
        code_filter = query_params.get('code')
        if code_filter:
            query = query.filter(AiAuditResponsePattern.condition == code_filter)

        # Order by condition (code) for consistent ordering
        patterns = query.order_by(AiAuditResponsePattern.condition).all()

        # Serialize patterns
        pattern_list = []
        for pattern in patterns:
            pattern_list.append({
                'id': pattern.id,
                'name': pattern.name,
                'condition': pattern.condition,
                'priority': pattern.priority,
                'pattern': pattern.pattern,
                'organization_id': pattern.organization_id,
                'material_id': pattern.material_id,
                'created_date': pattern.created_date.isoformat() if pattern.created_date else None,
                'updated_date': pattern.updated_date.isoformat() if pattern.updated_date else None
            })

        logger.info(f"Found {len(pattern_list)} response patterns")

        return {
            'success': True,
            'message': f'Found {len(pattern_list)} response patterns',
            'data': pattern_list
        }

    except Exception as e:
        logger.error(f"Error listing response patterns: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise APIException(f'Failed to list response patterns: {str(e)}')


def handle_create_response_pattern(
    db_session: Any,
    data: Dict[str, Any],
    organization_id: int
) -> Dict[str, Any]:
    """
    POST /api/transaction_audit/responses
    Create a new response pattern

    Request body:
    {
        "condition": "wc",  // Required: code (ncm, cc, wc, ui, hc, lc, pe, ie)
        "pattern": "จากรูป {{claimed_type}} ตรวจพบว่าเป็น {{detect_type}}..."  // Required
    }
    """
    try:
        # Validate required fields
        condition = data.get('condition')
        pattern = data.get('pattern')
        material_id = data.get('material_id')  # Optional: NULL = applies to all materials

        if not condition:
            raise ValidationException('Condition (code) is required')

        if not pattern:
            raise ValidationException('Pattern is required')

        # Validate condition is one of the allowed codes
        valid_codes = ['ncm', 'cc', 'wc', 'ui', 'hc', 'lc', 'pe', 'ie']
        if condition not in valid_codes:
            raise ValidationException(f'Invalid code. Must be one of: {", ".join(valid_codes)}')

        # Check if pattern already exists for this code, material_id, and organization
        # Same condition can exist multiple times if material_id is different
        query_conditions = [
            AiAuditResponsePattern.organization_id == organization_id,
            AiAuditResponsePattern.condition == condition,
            AiAuditResponsePattern.is_active == True,
            AiAuditResponsePattern.deleted_date.is_(None)
        ]

        # Add material_id check - must match exactly (NULL = NULL, or specific ID = specific ID)
        if material_id is None:
            query_conditions.append(AiAuditResponsePattern.material_id.is_(None))
        else:
            query_conditions.append(AiAuditResponsePattern.material_id == material_id)

        existing = db_session.query(AiAuditResponsePattern).filter(
            and_(*query_conditions)
        ).first()

        if existing:
            material_desc = 'all materials' if material_id is None else f'material ID {material_id}'
            raise ValidationException(f'Response pattern for code "{condition}" and {material_desc} already exists. Please edit the existing one.')

        # Create new pattern
        # Use code as name
        new_pattern = AiAuditResponsePattern(
            name=condition,
            condition=condition,
            priority=1000,  # Fixed priority
            pattern=pattern,
            organization_id=organization_id,
            material_id=material_id
        )

        db_session.add(new_pattern)
        db_session.commit()
        db_session.refresh(new_pattern)

        logger.info(f"Created response pattern {new_pattern.id} for code '{condition}'")

        return {
            'success': True,
            'message': f'Response pattern for code "{condition}" created successfully',
            'data': {
                'id': new_pattern.id,
                'name': new_pattern.name,
                'condition': new_pattern.condition,
                'priority': new_pattern.priority,
                'pattern': new_pattern.pattern,
                'organization_id': new_pattern.organization_id,
                'material_id': new_pattern.material_id,
                'created_date': new_pattern.created_date.isoformat() if new_pattern.created_date else None
            }
        }

    except (ValidationException, BadRequestException):
        db_session.rollback()
        raise
    except Exception as e:
        db_session.rollback()
        logger.error(f"Error creating response pattern: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise APIException(f'Failed to create response pattern: {str(e)}')


def handle_get_response_pattern(
    db_session: Any,
    pattern_id: int,
    organization_id: int
) -> Dict[str, Any]:
    """
    GET /api/transaction_audit/responses/{id}
    Get a single response pattern by ID
    """
    try:
        pattern = db_session.query(AiAuditResponsePattern).filter(
            and_(
                AiAuditResponsePattern.id == pattern_id,
                AiAuditResponsePattern.organization_id == organization_id,
                AiAuditResponsePattern.is_active == True,
                AiAuditResponsePattern.deleted_date.is_(None)
            )
        ).first()

        if not pattern:
            raise NotFoundException(f'Response pattern {pattern_id} not found')

        return {
            'success': True,
            'data': {
                'id': pattern.id,
                'name': pattern.name,
                'condition': pattern.condition,
                'priority': pattern.priority,
                'pattern': pattern.pattern,
                'organization_id': pattern.organization_id,
                'material_id': pattern.material_id,
                'created_date': pattern.created_date.isoformat() if pattern.created_date else None,
                'updated_date': pattern.updated_date.isoformat() if pattern.updated_date else None
            }
        }

    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error getting response pattern: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise APIException(f'Failed to get response pattern: {str(e)}')


def handle_update_response_pattern(
    db_session: Any,
    pattern_id: int,
    data: Dict[str, Any],
    organization_id: int
) -> Dict[str, Any]:
    """
    PUT /api/transaction_audit/responses/{id}
    Update an existing response pattern

    Request body:
    {
        "pattern": "updated pattern text",  // Required: pattern text
        "material_id": 77  // Optional: can update material_id
    }

    Note: Condition (code) cannot be changed after creation
    """
    try:
        # Find pattern
        pattern = db_session.query(AiAuditResponsePattern).filter(
            and_(
                AiAuditResponsePattern.id == pattern_id,
                AiAuditResponsePattern.organization_id == organization_id,
                AiAuditResponsePattern.is_active == True,
                AiAuditResponsePattern.deleted_date.is_(None)
            )
        ).first()

        if not pattern:
            raise NotFoundException(f'Response pattern {pattern_id} not found')

        # Update pattern text if provided
        new_pattern_text = data.get('pattern')
        if new_pattern_text:
            pattern.pattern = new_pattern_text
        else:
            raise ValidationException('Pattern text is required')

        # Update material_id if provided (can be NULL or a specific ID)
        if 'material_id' in data:
            new_material_id = data.get('material_id')

            # Check if another pattern exists with same condition + new material_id combination
            query_conditions = [
                AiAuditResponsePattern.organization_id == organization_id,
                AiAuditResponsePattern.condition == pattern.condition,
                AiAuditResponsePattern.is_active == True,
                AiAuditResponsePattern.deleted_date.is_(None),
                AiAuditResponsePattern.id != pattern_id  # Exclude current pattern
            ]

            if new_material_id is None:
                query_conditions.append(AiAuditResponsePattern.material_id.is_(None))
            else:
                query_conditions.append(AiAuditResponsePattern.material_id == new_material_id)

            existing = db_session.query(AiAuditResponsePattern).filter(
                and_(*query_conditions)
            ).first()

            if existing:
                material_desc = 'all materials' if new_material_id is None else f'material ID {new_material_id}'
                raise ValidationException(f'Response pattern for code "{pattern.condition}" and {material_desc} already exists.')

            pattern.material_id = new_material_id

        db_session.commit()
        db_session.refresh(pattern)

        logger.info(f"Updated response pattern {pattern_id}")

        return {
            'success': True,
            'message': 'Response pattern updated successfully',
            'data': {
                'id': pattern.id,
                'name': pattern.name,
                'condition': pattern.condition,
                'priority': pattern.priority,
                'pattern': pattern.pattern,
                'organization_id': pattern.organization_id,
                'material_id': pattern.material_id,
                'updated_date': pattern.updated_date.isoformat() if pattern.updated_date else None
            }
        }

    except (NotFoundException, ValidationException):
        db_session.rollback()
        raise
    except Exception as e:
        db_session.rollback()
        logger.error(f"Error updating response pattern: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise APIException(f'Failed to update response pattern: {str(e)}')


def handle_delete_response_pattern(
    db_session: Any,
    pattern_id: int,
    organization_id: int
) -> Dict[str, Any]:
    """
    DELETE /api/transaction_audit/responses/{id}
    Delete (soft delete) a response pattern
    """
    try:
        from datetime import datetime

        # Find pattern
        pattern = db_session.query(AiAuditResponsePattern).filter(
            and_(
                AiAuditResponsePattern.id == pattern_id,
                AiAuditResponsePattern.organization_id == organization_id,
                AiAuditResponsePattern.is_active == True,
                AiAuditResponsePattern.deleted_date.is_(None)
            )
        ).first()

        if not pattern:
            raise NotFoundException(f'Response pattern {pattern_id} not found')

        # Soft delete
        pattern.deleted_date = datetime.utcnow()
        pattern.is_active = False

        db_session.commit()

        logger.info(f"Deleted response pattern {pattern_id}")

        return {
            'success': True,
            'message': 'Response pattern deleted successfully',
            'data': {
                'id': pattern_id,
                'deleted_date': pattern.deleted_date.isoformat() if pattern.deleted_date else None
            }
        }

    except NotFoundException:
        db_session.rollback()
        raise
    except Exception as e:
        db_session.rollback()
        logger.error(f"Error deleting response pattern: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise APIException(f'Failed to delete response pattern: {str(e)}')
