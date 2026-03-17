"""
Reward Setup Service - Organization-level reward program configuration
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from ...models.rewards.management import RewardSetup
from ...exceptions import APIException, NotFoundException, BadRequestException


class RewardSetupService:
    def __init__(self, db: Session):
        self.db = db

    def get_setup(self, organization_id: int) -> dict:
        """Get reward setup for an organization. Auto-creates with defaults if not found."""
        setup = (
            self.db.query(RewardSetup)
            .filter(
                RewardSetup.organization_id == organization_id,
                RewardSetup.deleted_date.is_(None),
            )
            .first()
        )
        if not setup:
            setup = RewardSetup(
                organization_id=organization_id,
                hash=uuid.uuid4().hex,
                points_rounding_method="floor",
                timezone="Asia/Bangkok",
                cost_per_point=Decimal("0.25"),
                qr_code_size=200,
                qr_error_correction="M",
            )
            self.db.add(setup)
            self.db.flush()

        return {
            "id": setup.id,
            "organization_id": setup.organization_id,
            "program_name": setup.program_name,
            "program_name_local": setup.program_name_local,
            "points_rounding_method": setup.points_rounding_method,
            "timezone": setup.timezone,
            "cost_per_point": float(setup.cost_per_point) if setup.cost_per_point is not None else None,
            "qr_code_size": setup.qr_code_size,
            "qr_error_correction": setup.qr_error_correction,
            "receipt_template": setup.receipt_template,
            "hash": setup.hash,
            "welcome_message": setup.welcome_message,
            "created_date": setup.created_date.isoformat() if setup.created_date else None,
            "updated_date": setup.updated_date.isoformat() if setup.updated_date else None,
        }

    def upsert_setup(self, organization_id: int, data: dict) -> dict:
        """Create or update reward setup for an organization."""
        setup = (
            self.db.query(RewardSetup)
            .filter(
                RewardSetup.organization_id == organization_id,
                RewardSetup.deleted_date.is_(None),
            )
            .first()
        )

        updatable_fields = [
            "program_name", "program_name_local", "points_rounding_method",
            "timezone", "cost_per_point", "qr_code_size", "qr_error_correction",
            "receipt_template", "welcome_message",
        ]

        if setup:
            for field in updatable_fields:
                if field in data:
                    setattr(setup, field, data[field])
        else:
            setup = RewardSetup(
                organization_id=organization_id,
                hash=uuid.uuid4().hex,
            )
            for field in updatable_fields:
                if field in data:
                    setattr(setup, field, data[field])
            self.db.add(setup)

        self.db.flush()

        return self.get_setup(organization_id)
