"""
Audit Rules Management Service
Handles CRUD operations for audit rules with business logic
"""

from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy import and_, or_, func, text
import logging

from ....models.audit_rules import AuditRule, RuleType
from ....exceptions import ValidationException, NotFoundException, BadRequestException

logger = logging.getLogger(__name__)


class AuditRulesService:
    """
    Service for managing audit rules with business logic
    """

    def __init__(self, db: Session):
        self.db = db

    # ========== CRUD OPERATIONS ==========

    def create_rule(self, rule_data: Dict[str, Any], created_by_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Create a new audit rule with validation
        """
        try:
            # Validate rule data
            validation_result = self._validate_rule_data(rule_data)
            if not validation_result['valid']:
                error_messages = '; '.join(validation_result['errors'])
                raise ValidationException(f'Rule validation failed: {error_messages}')

            # Check if rule_id is unique
            existing_rule = self.db.query(AuditRule).filter(AuditRule.rule_id == rule_data['rule_id']).first()
            if existing_rule:
                raise ValidationException(f'Rule ID {rule_data["rule_id"]} already exists')

            # Create rule
            new_rule = AuditRule(
                rule_id=rule_data['rule_id'],
                rule_type=RuleType(rule_data['rule_type']),
                rule_name=rule_data['rule_name'],
                process=rule_data.get('process'),
                condition=rule_data.get('condition'),
                thresholds=rule_data.get('thresholds'),
                metrics=rule_data.get('metrics'),
                actions=rule_data.get('actions', []),
                is_global=rule_data.get('is_global', False),  # Default to False for organization-specific rules
                organization_id=rule_data.get('organization_id'),
                is_active=rule_data.get('is_active', True)
            )

            self.db.add(new_rule)
            self.db.commit()
            self.db.refresh(new_rule)

            logger.info(f"Created audit rule: {new_rule.rule_id}")

            return {
                'success': True,
                'rule': self._serialize_rule(new_rule),
                'message': f'Audit rule {new_rule.rule_id} created successfully'
            }

        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"Integrity error creating rule: {str(e)}")
            raise ValidationException('Rule creation failed due to data constraint violation')

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Database error creating rule: {str(e)}")
            raise Exception(f'Database error: {str(e)}')

    def get_rule_by_id(self, rule_id: int) -> Dict[str, Any]:
        """
        Get audit rule by ID
        """
        try:
            rule = self.db.query(AuditRule).filter(
                and_(
                    AuditRule.id == rule_id,
                    AuditRule.deleted_date.is_(None)
                )
            ).first()

            if not rule:
                raise NotFoundException(f'Audit rule with ID {rule_id} not found')

            return {
                'success': True,
                'rule': self._serialize_rule(rule)
            }

        except SQLAlchemyError as e:
            logger.error(f"Database error fetching rule {rule_id}: {str(e)}")
            raise Exception(f'Database error: {str(e)}')

    def get_rules_with_filters(
        self,
        filters: Optional[Dict[str, Any]] = None,
        page: int = 1,
        page_size: int = 50,
        sort_by: str = 'created_date',
        sort_order: str = 'desc'
    ) -> Dict[str, Any]:
        """
        Get audit rules with filtering and pagination
        """
        try:
            query = self.db.query(AuditRule).filter(AuditRule.deleted_date.is_(None))

            print(filters)
            # Apply filters
            if filters:
                # Filter by rule type
                if filters.get('rule_type'):
                    query = query.filter(AuditRule.rule_type == RuleType(filters['rule_type']))

                # Filter by active status
                if filters.get('is_active') is not None:
                    query = query.filter(AuditRule.is_active == filters['is_active'])

                # Filter by global status
                if filters.get('is_global') is not None:
                    query = query.filter(AuditRule.is_global == filters['is_global'])

                # Filter by organization
                if filters.get('organization_id'):
                    query = query.filter(AuditRule.organization_id == filters['organization_id'])

                # Text search in rule name, rule_id, or condition
                if filters.get('search'):
                    search_term = f"%{filters['search']}%"
                    query = query.filter(
                        or_(
                            AuditRule.rule_name.ilike(search_term),
                            AuditRule.rule_id.ilike(search_term),
                            AuditRule.condition.ilike(search_term),
                            AuditRule.process.ilike(search_term)
                        )
                    )

            # Get total count
            total_count = query.count()

            # Apply sorting
            if sort_by and hasattr(AuditRule, sort_by):
                if sort_order.lower() == 'desc':
                    query = query.order_by(getattr(AuditRule, sort_by).desc())
                else:
                    query = query.order_by(getattr(AuditRule, sort_by).asc())

            # Apply pagination
            offset = (page - 1) * page_size
            rules = query.offset(offset).limit(page_size).all()

            # Get rule type counts
            rule_type_counts = self._get_rule_type_counts(filters)

            return {
                'success': True,
                'data': [self._serialize_rule(rule) for rule in rules],
                'meta': {
                    'page': page,
                    'size': page_size,
                    'total': total_count,
                    'total_pages': (total_count + page_size - 1) // page_size,
                    'has_more': offset + page_size < total_count
                },
                'aggregations': {
                    'rule_type_counts': rule_type_counts,
                    'active_count': len([r for r in rules if r.is_active]),
                    'global_count': len([r for r in rules if r.is_global])
                }
            }

        except SQLAlchemyError as e:
            logger.error(f"Database error fetching rules: {str(e)}")
            raise Exception(f'Database error: {str(e)}')

    def update_rule(self, rule_id: int, update_data: Dict[str, Any], updated_by_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Update audit rule with validation
        """
        try:
            rule = self.db.query(AuditRule).filter(
                and_(
                    AuditRule.id == rule_id,
                    AuditRule.deleted_date.is_(None)
                )
            ).first()

            if not rule:
                raise NotFoundException(f'Audit rule with ID {rule_id} not found')

            # Validate update data
            validation_result = self._validate_rule_data(update_data, is_update=True)
            if not validation_result['valid']:
                error_messages = '; '.join(validation_result['errors'])
                raise ValidationException(f'Rule validation failed: {error_messages}')

            # Check rule_id uniqueness if being changed
            if update_data.get('rule_id') and update_data['rule_id'] != rule.rule_id:
                existing_rule = self.db.query(AuditRule).filter(
                    and_(
                        AuditRule.rule_id == update_data['rule_id'],
                        AuditRule.id != rule_id
                    )
                ).first()
                if existing_rule:
                    raise ValidationException(f'Rule ID {update_data["rule_id"]} already exists')

            # Update fields
            for field, value in update_data.items():
                if hasattr(rule, field):
                    if field == 'rule_type' and value:
                        setattr(rule, field, RuleType(value))
                    else:
                        setattr(rule, field, value)

            self.db.commit()
            self.db.refresh(rule)

            logger.info(f"Updated audit rule: {rule.rule_id}")

            return {
                'success': True,
                'rule': self._serialize_rule(rule),
                'message': f'Audit rule {rule.rule_id} updated successfully'
            }

        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"Integrity error updating rule {rule_id}: {str(e)}")
            raise ValidationException('Rule update failed due to data constraint violation')

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Database error updating rule {rule_id}: {str(e)}")
            raise Exception(f'Database error: {str(e)}')

    def delete_rule(self, rule_id: int, deleted_by_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Soft delete audit rule
        """
        try:
            rule = self.db.query(AuditRule).filter(
                and_(
                    AuditRule.id == rule_id,
                    AuditRule.deleted_date.is_(None)
                )
            ).first()

            if not rule:
                raise NotFoundException(f'Audit rule with ID {rule_id} not found')

            # Soft delete
            from datetime import datetime, timezone
            rule.deleted_date = datetime.now(timezone.utc)
            rule.is_active = False

            self.db.commit()

            logger.info(f"Deleted audit rule: {rule.rule_id}")

            return {
                'success': True,
                'message': f'Audit rule {rule.rule_id} deleted successfully'
            }

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Database error deleting rule {rule_id}: {str(e)}")
            raise Exception(f'Database error: {str(e)}')

    # ========== SPECIALIZED QUERIES ==========

    def get_active_rules(self, organization_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Get all active rules (global and organization-specific)
        """
        try:
            if organization_id:
                # Get both global rules and organization-specific rules
                query = self.db.query(AuditRule).filter(
                    and_(
                        AuditRule.deleted_date.is_(None),
                        AuditRule.is_active == True,
                        or_(
                            AuditRule.is_global == True,
                            AuditRule.organization_id == organization_id
                        )
                    )
                )

                rules = query.order_by(AuditRule.rule_type, AuditRule.rule_id).all()

                # Debug logging
                logger.info(f"Found {len(rules)} active rules for organization {organization_id}")

                # Also check total rules in database for debugging
                total_rules = self.db.query(AuditRule).filter(AuditRule.deleted_date.is_(None)).count()
                active_rules = self.db.query(AuditRule).filter(
                    and_(AuditRule.deleted_date.is_(None), AuditRule.is_active == True)
                ).count()
                global_rules = self.db.query(AuditRule).filter(
                    and_(AuditRule.deleted_date.is_(None), AuditRule.is_global == True)
                ).count()

                logger.info(f"DB Stats: Total rules: {total_rules}, Active rules: {active_rules}, Global rules: {global_rules}")

                return {
                    'success': True,
                    'data': [self._serialize_rule(rule) for rule in rules],
                    'meta': {
                        'total': len(rules),
                        'organization_id': organization_id,
                        'debug_stats': {
                            'total_rules_in_db': total_rules,
                            'active_rules_in_db': active_rules,
                            'global_rules_in_db': global_rules
                        }
                    }
                }
            else:
                # No organization ID - get all active rules
                filters = {'is_active': True}
                return self.get_rules_with_filters(filters, page_size=1000)

        except Exception as e:
            logger.error(f"Error in get_active_rules: {str(e)}")
            raise

    def get_rules_by_type(self, rule_type: str) -> Dict[str, Any]:
        """
        Get rules by specific type
        """
        try:
            rule_type_enum = RuleType(rule_type)
        except ValueError:
            raise ValidationException(f'Invalid rule type: {rule_type}')

        filters = {'rule_type': rule_type, 'is_active': True}
        return self.get_rules_with_filters(filters, page_size=1000)

    def get_global_rules(self) -> Dict[str, Any]:
        """
        Get all global rules
        """
        filters = {'is_global': True, 'is_active': True}
        return self.get_rules_with_filters(filters, page_size=1000)

    # ========== UTILITY METHODS ==========

    def _validate_rule_data(self, rule_data: Dict[str, Any], is_update: bool = False) -> Dict[str, Any]:
        """
        Validate audit rule data
        """
        errors = []

        # Required fields for create
        if not is_update:
            required_fields = ['rule_id', 'rule_type', 'rule_name']
            for field in required_fields:
                if not rule_data.get(field):
                    errors.append(f'{field} is required')

        # Validate rule_type
        if rule_data.get('rule_type'):
            try:
                RuleType(rule_data['rule_type'])
            except ValueError:
                valid_types = [rt.value for rt in RuleType]
                errors.append(f'Invalid rule_type. Must be one of: {", ".join(valid_types)}')

        # Validate rule_id format
        if rule_data.get('rule_id'):
            rule_id = rule_data['rule_id']
            if len(rule_id) > 20:
                errors.append('rule_id must be 20 characters or less')

        # Validate rule_name length
        if rule_data.get('rule_name'):
            if len(rule_data['rule_name']) > 500:
                errors.append('rule_name must be 500 characters or less')

        # Validate actions format
        if rule_data.get('actions'):
            if not isinstance(rule_data['actions'], list):
                errors.append('actions must be a list')
            else:
                for i, action in enumerate(rule_data['actions']):
                    if not isinstance(action, dict):
                        errors.append(f'actions[{i}] must be an object')
                        continue

                    if 'type' not in action:
                        errors.append(f'actions[{i}] must have a "type" field')
                    elif action['type'] not in ['system_action', 'human_action', 'recommendations']:
                        errors.append(f'actions[{i}].type must be one of: system_action, human_action, recommendations')

                    if 'action' not in action:
                        errors.append(f'actions[{i}] must have an "action" field')

        # Validate organization_id if not global
        if not rule_data.get('is_global', True) and not rule_data.get('organization_id'):
            errors.append('organization_id is required for non-global rules')

        return {
            'valid': len(errors) == 0,
            'errors': errors
        }

    def _get_rule_type_counts(self, filters: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
        """
        Get count of rules by type
        """
        try:
            query = self.db.query(AuditRule.rule_type, func.count(AuditRule.id)).filter(
                and_(
                    AuditRule.deleted_date.is_(None),
                    AuditRule.is_active == True
                )
            ).group_by(AuditRule.rule_type)

            # Apply organization filter if specified
            if filters and filters.get('organization_id'):
                query = query.filter(
                    or_(
                        AuditRule.is_global == True,
                        AuditRule.organization_id == filters['organization_id']
                    )
                )

            results = query.all()

            return {rule_type.value: count for rule_type, count in results}

        except SQLAlchemyError as e:
            logger.error(f"Error getting rule type counts: {str(e)}")
            return {}

    def _serialize_rule(self, rule: AuditRule) -> Dict[str, Any]:
        """
        Serialize audit rule for API response
        """
        return {
            'id': rule.id,
            'rule_id': rule.rule_id,
            'rule_type': rule.rule_type.value,
            'rule_name': rule.rule_name,
            'process': rule.process,
            'condition': rule.condition,
            'thresholds': rule.thresholds,
            'metrics': rule.metrics,
            'actions': rule.actions or [],
            'is_global': rule.is_global,
            'organization_id': rule.organization_id,
            'is_active': rule.is_active,
            'created_date': rule.created_date.isoformat() if rule.created_date else None,
            'updated_date': rule.updated_date.isoformat() if rule.updated_date else None,
            'deleted_date': rule.deleted_date.isoformat() if rule.deleted_date else None
        }