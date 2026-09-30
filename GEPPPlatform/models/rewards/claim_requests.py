"""
Self-submitted claim requests (Rewards "Admin tools").

A non-staff member's own claim is kept here, one row per item, until an admin approves it.
The real reward_point_transactions row is created only on approval and soft-deleted again
if the claim is later rejected, so no point/weight aggregate ever sees pending or rejected
claims. Status is kept in step with the waste transaction record the claim created (both
directions): see `sync_claim_requests_before_flush` below and ClaimRequestService.
"""

import logging

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, DateTime, event, inspect
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session
from sqlalchemy.types import DECIMAL

from ..base import Base, BaseModel

logger = logging.getLogger(__name__)


class RewardClaimRequest(Base, BaseModel):
    __tablename__ = 'reward_claim_requests'

    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    reward_user_id = Column(BigInteger, ForeignKey('reward_users.id'), nullable=False)
    organization_reward_user_id = Column(BigInteger, ForeignKey('organization_reward_users.id'), nullable=True)
    reward_campaign_id = Column(BigInteger, ForeignKey('reward_campaigns.id'), nullable=False)
    reward_activity_materials_id = Column(BigInteger, ForeignKey('reward_activity_materials.id'), nullable=False)
    droppoint_id = Column(BigInteger, ForeignKey('droppoints.id'), nullable=True)
    submission_uid = Column(String(36), nullable=False)
    value = Column(DECIMAL(10, 4), nullable=False)
    unit = Column(String(50), nullable=True)
    requested_points = Column(DECIMAL(10, 2), nullable=False, default=0)
    status = Column(String(16), nullable=False, default='pending')  # pending / approved / rejected
    image_ids = Column(JSONB, nullable=True)
    note = Column(Text, nullable=True)
    transaction_id = Column(BigInteger, ForeignKey('transactions.id'), nullable=True)
    transaction_record_id = Column(BigInteger, ForeignKey('transaction_records.id'), nullable=True)
    reward_point_transaction_id = Column(BigInteger, nullable=True)  # reward_point_transactions.id while approved
    reviewed_by_id = Column(BigInteger, nullable=True)
    reviewed_date = Column(DateTime(timezone=True), nullable=True)
    review_note = Column(Text, nullable=True)
    submitted_date = Column(DateTime(timezone=True), nullable=False)


# ---------------------------------------------------------------------------
# Waste transaction → claim request sync
# ---------------------------------------------------------------------------
# Every path that changes a waste transaction's status (manual audit per record, per
# transaction and in bulk, PUT /api/transactions, record edits resetting to pending, AI
# audit) goes through the ORM, so one flush hook keeps the reward side in step without
# touching each of them. Only reward-created rows are inspected, so ordinary transactions
# pay a type check and nothing else.

_WATCHED = ('status', 'deleted_date')


def _changed(obj, attrs=_WATCHED) -> bool:
    state = inspect(obj)
    return any(state.attrs[a].history.has_changes() for a in attrs if a in state.attrs)


def sync_claim_requests_before_flush(session, flush_context, instances):
    if session.info.get('_claim_request_sync_running'):
        return
    from ..transactions.transactions import Transaction
    from ..transactions.transaction_records import TransactionRecord

    record_ids, transaction_ids = set(), set()
    for obj in list(session.dirty):
        if isinstance(obj, TransactionRecord):
            if getattr(obj, 'transaction_type', None) == 'rewards' and obj.id and _changed(obj):
                record_ids.add(obj.id)
        elif isinstance(obj, Transaction):
            if getattr(obj, 'transaction_method', None) == 'reward' and obj.id and _changed(obj):
                transaction_ids.add(obj.id)
    if not record_ids and not transaction_ids:
        return

    session.info['_claim_request_sync_running'] = True
    try:
        with session.no_autoflush:
            from ...services.rewards.claim_request_service import ClaimRequestService
            ClaimRequestService(session).sync_from_waste(record_ids=record_ids, transaction_ids=transaction_ids)
    except Exception as exc:  # the waste-side action must never fail because of rewards
        logger.warning("[rewards] claim request sync skipped: %s", exc, exc_info=True)
    finally:
        session.info.pop('_claim_request_sync_running', None)


def register_claim_request_sync() -> None:
    if not event.contains(Session, 'before_flush', sync_claim_requests_before_flush):
        event.listen(Session, 'before_flush', sync_claim_requests_before_flush)
