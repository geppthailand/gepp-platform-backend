"""
Campaign Expense Service — per-campaign expense ledger entries.

Entry-level granularity: each receipt/expense is a row with date, amount, vendor, note.
The "ของรางวัล" category is locked from this ledger (its amount is computed from
inventory deposits in cost_report_service).
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from ...models.rewards.management import (
    RewardCampaign, RewardCampaignExpense, RewardExpenseCategory,
)
from ...exceptions import NotFoundException, BadRequestException


def _parse_date(s):
    if not s:
        return None
    if isinstance(s, datetime):
        return s
    try:
        # Accept date-only "YYYY-MM-DD" or full ISO
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        raise BadRequestException(f"Invalid date format: {s}")


class CampaignExpenseService:
    def __init__(self, db: Session):
        self.db = db

    def _to_dict(self, item: RewardCampaignExpense, category_name: str | None = None) -> dict:
        return {
            "id": item.id,
            "organization_id": item.organization_id,
            "reward_campaign_id": item.reward_campaign_id,
            "expense_category_id": item.expense_category_id,
            "category_name": category_name,
            "amount_baht": float(item.amount_baht) if item.amount_baht is not None else 0.0,
            "expense_date": item.expense_date.isoformat() if item.expense_date else None,
            "vendor": item.vendor,
            "note": item.note,
            "receipt_file_id": item.receipt_file_id,
            "created_date": item.created_date.isoformat() if item.created_date else None,
        }

    def list(
        self,
        organization_id: int,
        campaign_id: int | None = None,
        category_id: int | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict]:
        # [V3-COST-LEDGER] Join category for name in one round-trip; expense ledger only
        # surfaces admin-entered rows. Inventory cost is computed separately in cost_report.
        df = _parse_date(date_from)
        dt = _parse_date(date_to)
        q = (
            self.db.query(RewardCampaignExpense, RewardExpenseCategory.name)
            .join(
                RewardExpenseCategory,
                RewardExpenseCategory.id == RewardCampaignExpense.expense_category_id,
            )
            .filter(
                RewardCampaignExpense.organization_id == organization_id,
                RewardCampaignExpense.deleted_date.is_(None),
            )
        )
        if campaign_id is not None:
            q = q.filter(RewardCampaignExpense.reward_campaign_id == campaign_id)
        if category_id is not None:
            q = q.filter(RewardCampaignExpense.expense_category_id == category_id)
        if df is not None:
            q = q.filter(RewardCampaignExpense.expense_date >= df)
        if dt is not None:
            q = q.filter(RewardCampaignExpense.expense_date <= dt)
        rows = q.order_by(
            RewardCampaignExpense.expense_date.desc(),
            RewardCampaignExpense.id.desc(),
        ).all()
        return [self._to_dict(row[0], category_name=row[1]) for row in rows]

    def create(self, organization_id: int, data: dict) -> dict:
        campaign_id = data.get("reward_campaign_id")
        category_id = data.get("expense_category_id")
        amount = data.get("amount_baht")
        expense_date = _parse_date(data.get("expense_date"))

        if not campaign_id:
            raise BadRequestException("reward_campaign_id is required")
        if not category_id:
            raise BadRequestException("expense_category_id is required")
        if amount is None:
            raise BadRequestException("amount_baht is required")
        if expense_date is None:
            raise BadRequestException("expense_date is required")
        try:
            amount_dec = Decimal(str(amount))
        except Exception:
            raise BadRequestException("amount_baht must be a number")
        if amount_dec < 0:
            raise BadRequestException("amount_baht cannot be negative")

        # Validate campaign + category belong to this org
        camp = (
            self.db.query(RewardCampaign)
            .filter(
                RewardCampaign.id == campaign_id,
                RewardCampaign.organization_id == organization_id,
                RewardCampaign.deleted_date.is_(None),
            )
            .first()
        )
        if not camp:
            raise NotFoundException("Campaign not found")

        cat = (
            self.db.query(RewardExpenseCategory)
            .filter(
                RewardExpenseCategory.id == category_id,
                RewardExpenseCategory.organization_id == organization_id,
                RewardExpenseCategory.deleted_date.is_(None),
            )
            .first()
        )
        if not cat:
            raise NotFoundException("Category not found")
        if cat.is_inventory:
            # Inventory cost is computed from deposits, not entered here.
            raise BadRequestException(
                "Cannot create expense in the 'ของรางวัล' category — its cost is auto-computed from inventory deposits"
            )

        item = RewardCampaignExpense(
            organization_id=organization_id,
            reward_campaign_id=campaign_id,
            expense_category_id=category_id,
            amount_baht=amount_dec,
            expense_date=expense_date,
            vendor=(data.get("vendor") or None),
            note=(data.get("note") or None),
            receipt_file_id=data.get("receipt_file_id"),
        )
        self.db.add(item)
        self.db.flush()
        return self._to_dict(item, category_name=cat.name)

    def update(self, id: int, organization_id: int, data: dict) -> dict:
        item = self._get_or_404(id, organization_id)
        if "expense_category_id" in data and data["expense_category_id"]:
            cat_id = data["expense_category_id"]
            cat = (
                self.db.query(RewardExpenseCategory)
                .filter(
                    RewardExpenseCategory.id == cat_id,
                    RewardExpenseCategory.organization_id == organization_id,
                    RewardExpenseCategory.deleted_date.is_(None),
                )
                .first()
            )
            if not cat:
                raise NotFoundException("Category not found")
            if cat.is_inventory:
                raise BadRequestException(
                    "Cannot move expense into 'ของรางวัล' — inventory cost is auto-computed"
                )
            item.expense_category_id = cat_id
        if "amount_baht" in data:
            try:
                item.amount_baht = Decimal(str(data["amount_baht"]))
            except Exception:
                raise BadRequestException("amount_baht must be a number")
            if item.amount_baht < 0:
                raise BadRequestException("amount_baht cannot be negative")
        if "expense_date" in data and data["expense_date"]:
            item.expense_date = _parse_date(data["expense_date"])
        if "vendor" in data:
            item.vendor = data["vendor"] or None
        if "note" in data:
            item.note = data["note"] or None
        if "receipt_file_id" in data:
            item.receipt_file_id = data["receipt_file_id"]
        self.db.flush()

        cat_name = (
            self.db.query(RewardExpenseCategory.name)
            .filter(RewardExpenseCategory.id == item.expense_category_id)
            .scalar()
        )
        return self._to_dict(item, category_name=cat_name)

    def delete(self, id: int, organization_id: int) -> dict:
        item = self._get_or_404(id, organization_id)
        item.deleted_date = datetime.now(timezone.utc)
        self.db.flush()
        return {"id": id, "deleted": True}

    def _get_or_404(self, id: int, organization_id: int) -> RewardCampaignExpense:
        item = (
            self.db.query(RewardCampaignExpense)
            .filter(
                RewardCampaignExpense.id == id,
                RewardCampaignExpense.organization_id == organization_id,
                RewardCampaignExpense.deleted_date.is_(None),
            )
            .first()
        )
        if not item:
            raise NotFoundException("Expense entry not found")
        return item
