"""
Expense Category Service — Org-managed categories for the campaign expense ledger.

The "ของรางวัล" category is auto-seeded with is_inventory=True + is_system=True; its
amount in reports is computed from inventory deposits (not entered via this ledger).
Other categories (Manpower / Transport / Marketing / อื่น ๆ) are seeded on first
list call and are admin-editable.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ...models.rewards.management import RewardExpenseCategory, RewardCampaignExpense
from ...exceptions import NotFoundException, BadRequestException


# [V3-COST-LEDGER] Default categories seeded the first time an org accesses the ledger.
# Order = sort_order. "ของรางวัล" is locked (is_system=True + is_inventory=True).
_DEFAULT_SEED: list[dict] = [
    {"name": "ของรางวัล", "is_inventory": True,  "is_system": True,  "sort_order": 0},
    {"name": "Manpower",  "is_inventory": False, "is_system": False, "sort_order": 10},
    {"name": "Transport", "is_inventory": False, "is_system": False, "sort_order": 20},
    {"name": "Marketing", "is_inventory": False, "is_system": False, "sort_order": 30},
    {"name": "อื่น ๆ",    "is_inventory": False, "is_system": False, "sort_order": 40},
]


class ExpenseCategoryService:
    def __init__(self, db: Session):
        self.db = db

    def _to_dict(self, item: RewardExpenseCategory) -> dict:
        return {
            "id": item.id,
            "organization_id": item.organization_id,
            "name": item.name,
            "is_inventory": bool(item.is_inventory),
            "is_system": bool(item.is_system),
            "sort_order": item.sort_order,
        }

    def _ensure_seeded(self, organization_id: int) -> None:
        """Seed default categories the first time an org touches the ledger."""
        any_row = (
            self.db.query(RewardExpenseCategory.id)
            .filter(
                RewardExpenseCategory.organization_id == organization_id,
                RewardExpenseCategory.deleted_date.is_(None),
            )
            .first()
        )
        if any_row is not None:
            return
        for seed in _DEFAULT_SEED:
            self.db.add(RewardExpenseCategory(
                organization_id=organization_id,
                name=seed["name"],
                is_inventory=seed["is_inventory"],
                is_system=seed["is_system"],
                sort_order=seed["sort_order"],
            ))
        self.db.flush()

    def list(self, organization_id: int) -> list[dict]:
        self._ensure_seeded(organization_id)
        rows = (
            self.db.query(RewardExpenseCategory)
            .filter(
                RewardExpenseCategory.organization_id == organization_id,
                RewardExpenseCategory.deleted_date.is_(None),
            )
            .order_by(RewardExpenseCategory.sort_order.asc(), RewardExpenseCategory.id.asc())
            .all()
        )
        return [self._to_dict(r) for r in rows]

    def create(self, organization_id: int, data: dict) -> dict:
        name = (data.get("name") or "").strip()
        if not name:
            raise BadRequestException("Category name is required")

        dup = (
            self.db.query(RewardExpenseCategory)
            .filter(
                RewardExpenseCategory.organization_id == organization_id,
                RewardExpenseCategory.deleted_date.is_(None),
                RewardExpenseCategory.name.ilike(name),
            )
            .first()
        )
        if dup:
            raise BadRequestException(f"Category '{name}' already exists")

        item = RewardExpenseCategory(
            organization_id=organization_id,
            name=name,
            is_inventory=False,
            is_system=False,
            sort_order=int(data.get("sort_order") or 100),
        )
        self.db.add(item)
        self.db.flush()
        return self._to_dict(item)

    def update(self, id: int, organization_id: int, data: dict) -> dict:
        item = self._get_or_404(id, organization_id)
        # Allow rename of the locked inventory row (label only) since admin may want a
        # localized name. Hard-prevent flipping is_inventory/is_system from the API.
        if "name" in data:
            new_name = (data["name"] or "").strip()
            if not new_name:
                raise BadRequestException("Category name is required")
            item.name = new_name
        if "sort_order" in data:
            item.sort_order = int(data["sort_order"] or 0)
        self.db.flush()
        return self._to_dict(item)

    def delete(self, id: int, organization_id: int) -> dict:
        """Soft-delete. Refuses to delete system rows (e.g. the "ของรางวัล" inventory category)
        and refuses if any expense entry still references it."""
        item = self._get_or_404(id, organization_id)
        if item.is_system:
            raise BadRequestException("System category cannot be deleted")

        in_use = (
            self.db.query(RewardCampaignExpense)
            .filter(
                RewardCampaignExpense.expense_category_id == id,
                RewardCampaignExpense.deleted_date.is_(None),
            )
            .count()
        )
        if in_use > 0:
            raise BadRequestException(
                f"Cannot delete — {in_use} expense entry(s) still use this category"
            )

        item.deleted_date = datetime.now(timezone.utc)
        self.db.flush()
        return {"id": id, "deleted": True}

    def _get_or_404(self, id: int, organization_id: int) -> RewardExpenseCategory:
        item = (
            self.db.query(RewardExpenseCategory)
            .filter(
                RewardExpenseCategory.id == id,
                RewardExpenseCategory.organization_id == organization_id,
                RewardExpenseCategory.deleted_date.is_(None),
            )
            .first()
        )
        if not item:
            raise NotFoundException("Category not found")
        return item
