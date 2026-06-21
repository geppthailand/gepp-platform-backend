"""Shared in-memory SQLite harness for reward service tests.

Teaches the Postgres-only column types (JSONB, UUID) and BigInteger autoincrement
to work on SQLite, then exposes make_session() that creates just the reward tables
involved in walk-in / merge flows. Underscore-prefixed so pytest doesn't collect it.

IMPORTANT — test isolation: tests/crm_features/test_public_lead_capture.py replaces
``sqlalchemy`` / ``sqlalchemy.orm`` in sys.modules with MagicMocks at import time, and
that suite is collected before test_reward_* (c < t). To stay robust, ALL SQLAlchemy
work here is bound lazily inside make_session() — which runs during test execution,
after conftest's pytest_runtest_setup has restored the real sqlalchemy modules — never
at module import (collection) time.
"""

_INITIALIZED = False


def _ensure_compilers():
    """Register SQLite compilation for Postgres-only types (idempotent, once)."""
    global _INITIALIZED
    if _INITIALIZED:
        return
    from sqlalchemy import BigInteger
    from sqlalchemy.ext.compiler import compiles
    from sqlalchemy.dialects.postgresql import JSONB, UUID

    @compiles(JSONB, "sqlite")
    def _compile_jsonb_sqlite(element, compiler, **kw):  # pragma: no cover - test shim
        return "JSON"

    @compiles(UUID, "sqlite")
    def _compile_uuid_sqlite(element, compiler, **kw):  # pragma: no cover - test shim
        return "VARCHAR(36)"

    @compiles(BigInteger, "sqlite")
    def _compile_bigint_sqlite(element, compiler, **kw):  # pragma: no cover - test shim
        # SQLite only autoincrements INTEGER PRIMARY KEY (not BIGINT).
        return "INTEGER"

    _INITIALIZED = True


def make_session():
    """Fresh in-memory SQLite session with the reward tables created."""
    _ensure_compilers()

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from GEPPPlatform.models.base import Base
    from GEPPPlatform.models.rewards.redemptions import (
        RewardUser,
        OrganizationRewardUser,
        RewardRedemption,
        RewardStaffInvite,
        RewardUserMerge,
    )
    from GEPPPlatform.models.rewards.points import RewardPointTransaction
    from GEPPPlatform.models.rewards.catalog import RewardStock, RewardCatalog
    from GEPPPlatform.models.rewards.management import RewardCampaign, RewardCampaignCatalog

    tables = [
        RewardUser.__table__,
        OrganizationRewardUser.__table__,
        RewardPointTransaction.__table__,
        RewardRedemption.__table__,
        RewardStock.__table__,
        RewardStaffInvite.__table__,
        RewardUserMerge.__table__,
        # Catalog/campaign tables needed by the redeem flow (staff_redeem tests).
        RewardCampaign.__table__,
        RewardCampaignCatalog.__table__,
        RewardCatalog.__table__,
    ]
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=tables)
    return sessionmaker(bind=engine)()
