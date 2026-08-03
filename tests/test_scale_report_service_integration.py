"""Runs get_daily_summary against a real PostgreSQL instance.

The unit tests around this feature cover the day-window maths and the public
payload projection, but neither exercises the SQL. Several things can only fail
against a real server:

  * `GROUP BY` must list every non-aggregated selected column, or Postgres
    rejects the statement outright.
  * `Material.name_th` and `MainMaterial.name_th` collide by name; only the
    MainMaterial pair is labelled, so row attribute access has to resolve to
    the right one.
  * `DECIMAL` columns arrive as `Decimal`, which `json.dumps` cannot serialize.
  * The Bangkok window has to exclude a reading at exactly 17:00:00 UTC.

Only the columns the query touches are created — it is a column-only select, so
the rest of each model is irrelevant here. Skipped when no local Postgres is
reachable (the DSN matches run_local.sh's default).
"""

import json
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

from GEPPPlatform.libs.exceptions import UnauthorizedException
from GEPPPlatform.services.cores.scale_reports.scale_report_service import (
    get_daily_summary,
    to_public_payload,
)

_ADMIN_DSN = 'postgresql://postgres:@localhost:5432/postgres'
_PROBE_DB = 'scale_report_itest'
_PROBE_DSN = 'postgresql://postgres:@localhost:5432/' + _PROBE_DB

_SCHEMA = """
CREATE TABLE user_locations (
    id BIGINT PRIMARY KEY,
    display_name VARCHAR(255),
    name_th VARCHAR(255),
    name_en VARCHAR(255),
    organization_id BIGINT,
    deleted_date TIMESTAMPTZ
);
CREATE TABLE main_materials (
    id BIGINT PRIMARY KEY,
    name_th VARCHAR(255),
    name_en VARCHAR(255)
);
CREATE TABLE materials (
    id BIGINT PRIMARY KEY,
    name_th VARCHAR(255),
    name_en VARCHAR(255),
    unit_name_th VARCHAR(255),
    unit_name_en VARCHAR(255),
    color VARCHAR(7),
    calc_ghg DECIMAL(10,3)
);
CREATE TABLE transactions (
    id BIGINT PRIMARY KEY,
    origin_id BIGINT,
    organization_id BIGINT,
    transaction_date TIMESTAMP,
    deleted_date TIMESTAMPTZ
);
CREATE TABLE organization_setup (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT,
    version VARCHAR(50),
    root_nodes JSONB,
    hub_node JSONB,
    metadata JSONB,
    branch_level_name VARCHAR(255),
    building_level_name VARCHAR(255),
    floor_level_name VARCHAR(255),
    room_level_name VARCHAR(255),
    input_destination JSONB,
    show_all_location_options BOOLEAN,
    is_active BOOLEAN,
    created_date TIMESTAMPTZ DEFAULT now(),
    updated_date TIMESTAMPTZ,
    deleted_date TIMESTAMPTZ
);
CREATE TABLE transaction_records (
    id BIGSERIAL PRIMARY KEY,
    created_transaction_id BIGINT,
    material_id BIGINT,
    main_material_id BIGINT,
    category_id BIGINT,
    origin_weight_kg DECIMAL(15,4),
    origin_quantity DECIMAL(15,4),
    transaction_date TIMESTAMP,
    status VARCHAR(50),
    deleted_date TIMESTAMPTZ
);
"""

# Thai day 2026-07-26 spans UTC 2026-07-25 17:00 → 2026-07-26 17:00.
_FIXTURES = """
INSERT INTO user_locations (id, display_name, name_th, name_en, organization_id)
VALUES (1, 'ศูนย์รับซื้อ สาขาบางนา', 'สาขาบางนา', 'Bangna', 10),
       (2, 'สาขาอื่น', 'อื่น', 'Other', 99),
       (3, 'ชั้น 1', 'ชั้น 1', 'Floor 1', 10);

-- ผังองค์กร: จุด 1 (อาคาร) มีลูกคือจุด 3 (ชั้น) ตาชั่งตั้งอยู่ที่ชั้น
INSERT INTO organization_setup (organization_id, is_active, root_nodes)
VALUES (10, true, '[{"nodeId": 1, "children": [{"nodeId": 3, "children": []}]}]');

INSERT INTO main_materials (id, name_th, name_en) VALUES (7, 'พลาสติก', 'Plastic');

INSERT INTO materials (id, name_th, name_en, unit_name_th, unit_name_en, color, calc_ghg)
VALUES (100, 'ขวด PET ใส', 'Clear PET', 'กก.', 'kg', '#4CAF50', 2.000),
       (200, 'กระดาษลัง',  'Cardboard', 'กก.', 'kg', '#8D6E63', 1.500);

INSERT INTO transactions (id, origin_id, organization_id, transaction_date)
VALUES (1000, 1, 10, '2026-07-26 02:00:00'),
       (1001, 1, 10, '2026-07-26 09:00:00'),
       (1002, 1, 10, '2026-07-26 17:00:00'),   -- 00:00 Thai on the 27th
       (1003, 2, 99, '2026-07-26 03:00:00'),   -- different location
       (1004, 3, 10, '2026-07-26 04:00:00');   -- ชั้น 1 (ลูกของจุด 1)

INSERT INTO transaction_records
 (created_transaction_id, material_id, main_material_id, category_id,
  origin_weight_kg, origin_quantity, transaction_date, status, deleted_date)
VALUES
 (1000, 100,  7, 3, 10.0, 10.0, '2026-07-26 02:00:00', 'pending',  NULL),
 (1001, 100,  7, 3,  5.0,  5.0, '2026-07-26 09:00:00', NULL,       NULL),
 (1000, 200,  7, 3, 20.0, 20.0, '2026-07-26 02:30:00', 'pending',  NULL),
 (1001, NULL, 7, 3,  1.0,  1.0, '2026-07-26 10:00:00', NULL,       NULL),
 (1000, 100,  7, 3, 999.0, 999.0, '2026-07-26 02:00:00', 'rejected', NULL),
 (1000, 100,  7, 3, 888.0, 888.0, '2026-07-26 02:00:00', 'pending',  now()),
 (1002, 100,  7, 3, 777.0, 777.0, '2026-07-26 17:00:00', 'pending',  NULL),
 (1003, 100,  7, 3, 666.0, 666.0, '2026-07-26 03:00:00', 'pending',  NULL),
 -- ชั่งที่ "ชั้น 1" (ลูกของจุด 1) — ต้องไม่นับในยอดเฉพาะจุด แต่ต้องนับในยอดรวมกิ่ง
 (1004, 100,  7, 3,  50.0,  50.0, '2026-07-26 04:00:00', 'pending',  NULL);
"""

#: Weights that must never appear: rejected, soft-deleted, next Thai day, other site.
_EXCLUDED_WEIGHTS = (999.0, 888.0, 777.0, 666.0)


@pytest.fixture(scope='module')
def session():
    # exec_driver_sql, not text(): tests/crm_features/test_deliveries_csv.py
    # replaces sqlalchemy.text with an identity lambda *on the real module
    # object*, so text() elsewhere in the session returns a bare string and
    # Connection.execute rejects it. Going straight to the driver avoids
    # depending on that name at all.
    try:
        admin = create_engine(_ADMIN_DSN, isolation_level='AUTOCOMMIT')
        with admin.connect() as conn:
            conn.exec_driver_sql('DROP DATABASE IF EXISTS ' + _PROBE_DB)
            conn.exec_driver_sql('CREATE DATABASE ' + _PROBE_DB)
    except OperationalError as exc:
        # Genuinely no reachable server — skip. Anything else is a real
        # failure and must not be hidden behind a skip.
        pytest.skip('local PostgreSQL not reachable: {0}'.format(exc))

    engine = create_engine(_PROBE_DSN)
    with engine.begin() as conn:
        for statement in (_SCHEMA + _FIXTURES).split(';'):
            if statement.strip():
                conn.exec_driver_sql(statement)

    # sqlalchemy.orm.Session is overwritten with `object` by the same
    # polluting test (`_sqlalchemy.orm.Session = object`), so reach for the
    # class in its defining submodule, which nothing rebinds. Imported here
    # rather than at module scope so it resolves after conftest has restored
    # sys.modules for this test.
    from sqlalchemy.orm.session import Session as OrmSession

    db = OrmSession(engine)
    yield db
    db.close()
    engine.dispose()
    with admin.connect() as conn:
        conn.exec_driver_sql('DROP DATABASE IF EXISTS ' + _PROBE_DB)


@pytest.fixture(scope='module')
def summary(session):
    return get_daily_summary(session, origin_id=1, organization_id=10,
                             day=date(2026, 7, 26))


# ── totals ───────────────────────────────────────────────────────────────────

def test_totals_count_only_the_eligible_records(summary):
    # 10 + 5 (PET) + 20 (cardboard) + 1 (no material) = 36
    assert summary['totals']['weight_kg'] == 36.0
    assert summary['totals']['entries'] == 4
    assert summary['totals']['material_count'] == 3


def test_co2e_follows_weight_times_calc_ghg(summary):
    # 15×2.0 + 20×1.5 + 1×(no material → 0) = 60
    assert summary['totals']['co2e_kg'] == 60.0
    assert summary['totals']['trees_equivalent'] == 6.3      # 60 / 9.5
    assert summary['totals']['forest_rai_equivalent'] == 0.06  # 60 / 950


def test_first_and_last_entry_span_the_day(summary):
    assert summary['totals']['first_entry_at'] == '2026-07-26T02:00:00'
    assert summary['totals']['last_entry_at'] == '2026-07-26T10:00:00'


# ── exclusions ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize('weight', _EXCLUDED_WEIGHTS)
def test_ineligible_records_are_absent(summary, weight):
    assert weight not in [m['weight_kg'] for m in summary['materials']]


def test_reading_at_1700_utc_belongs_to_the_next_thai_day(session):
    """The 7-hour bug, end to end: this reading must be absent from the 26th
    and present on the 27th."""
    next_day = get_daily_summary(session, 1, 10, date(2026, 7, 27))
    assert next_day['totals']['weight_kg'] == 777.0


# ── shape ────────────────────────────────────────────────────────────────────

def test_records_without_a_material_still_count(summary):
    """Guards the outerjoin. An inner join would drop this row and quietly
    understate the day's total."""
    nameless = [m for m in summary['materials'] if m['material_id'] is None]
    assert len(nameless) == 1
    assert nameless[0]['weight_kg'] == 1.0


def test_material_names_resolve_to_material_not_main_material(summary):
    """`materials.name_th` and `main_materials.name_th` collide by name."""
    top = summary['materials'][0]
    assert top['name_th'] == 'กระดาษลัง'
    assert top['main_material_name_th'] == 'พลาสติก'


def test_materials_are_sorted_by_weight_descending(summary):
    weights = [m['weight_kg'] for m in summary['materials']]
    assert weights == sorted(weights, reverse=True)


def test_share_pct_is_relative_to_the_day_total(summary):
    by_name = {m['name_th']: m for m in summary['materials']}
    assert by_name['กระดาษลัง']['share_pct'] == 55.6   # 20 / 36
    assert by_name['ขวด PET ใส']['share_pct'] == 41.7  # 15 / 36


def test_payload_is_json_serialisable(summary):
    """DECIMAL columns arrive as Decimal, which json.dumps refuses."""
    assert isinstance(json.dumps(summary), str)


def test_location_details_are_included(summary):
    assert summary['location']['origin_id'] == 1
    assert summary['location']['display_name'] == 'ศูนย์รับซื้อ สาขาบางนา'


# ── empty and refused ────────────────────────────────────────────────────────

def test_a_day_with_no_readings_returns_zeros_not_an_error(session):
    """"Nobody came in today" is a valid answer, not a 404."""
    empty = get_daily_summary(session, 1, 10, date(2026, 1, 1))
    assert empty['totals']['weight_kg'] == 0.0
    assert empty['totals']['entries'] == 0
    assert empty['materials'] == []


def test_location_from_another_organization_is_refused(session):
    with pytest.raises(UnauthorizedException):
        get_daily_summary(session, origin_id=1, organization_id=999,
                          day=date(2026, 7, 26))


def test_public_payload_over_real_data_keeps_the_breakdown_but_not_ids(summary):
    """The public page shows what was collected, not the plumbing behind it."""
    public = to_public_payload(summary)
    # ใช้ยอดรวมทั้งกิ่ง ให้ตรงกับตัวเลขที่พนักงานเห็นตอนยื่น QR ให้ลูกค้า
    assert public['totals']['weight_kg'] == 86.0
    assert [m['name_th'] for m in public['materials']] == [
        'ขวด PET ใส', 'กระดาษลัง', None,
    ]
    for entry in public['materials']:
        assert 'material_id' not in entry
        assert 'category_id' not in entry
    # internal-only sections still never leave
    assert 'window_utc' not in public
    assert 'origin_id' not in public['location']


# ── ยอดเฉพาะจุด vs ยอดรวมทั้งกิ่ง ─────────────────────────────────────────────

def test_own_total_counts_only_the_location_itself(summary):
    """ตาชั่งตั้งที่ชั้น ยอด "เฉพาะอาคาร" จึงไม่รวม 50 กก. ของชั้น"""
    assert summary['totals']['weight_kg'] == 36.0


def test_subtree_total_rolls_up_the_children(summary):
    """หัวหน้าที่ดูแลระดับอาคารต้องเห็นของชั้นข้างใต้ด้วย ไม่ใช่ 0
    เพราะไม่มีใครชั่งโดยระบุตัวอาคารตรง ๆ"""
    assert summary['subtree']['totals']['weight_kg'] == 86.0   # 36 + 50
    assert summary['subtree']['has_descendants'] is True
    assert summary['subtree']['location_count'] == 2


def test_subtree_merges_the_same_material_across_locations(summary):
    """PET ถูกชั่งทั้งที่อาคารและที่ชั้น — ต้องยุบเป็นรายการเดียว ไม่ใช่สองแถว"""
    pet = [m for m in summary['subtree']['materials'] if m['name_th'] == 'ขวด PET ใส']
    assert len(pet) == 1
    assert pet[0]['weight_kg'] == 65.0        # 15 (อาคาร) + 50 (ชั้น)


def test_subtree_shares_add_up_against_the_subtree_total(summary):
    shares = sum(m['share_pct'] for m in summary['subtree']['materials'])
    assert 99.0 <= shares <= 101.0            # ปัดทศนิยมแล้วยังต้องใกล้ 100


def test_a_leaf_location_reports_itself_as_having_no_descendants(session):
    leaf = get_daily_summary(session, 3, 10, date(2026, 7, 26))
    assert leaf['totals']['weight_kg'] == 50.0
    assert leaf['subtree']['totals']['weight_kg'] == 50.0
    assert leaf['subtree']['has_descendants'] is False


# ── แตกยอดรายจุด (กล่อง "แยกตามจุด" บนหน้าเว็บ) ────────────────────────────────

def test_locations_split_the_branch_by_where_it_was_weighed(summary):
    locations = summary['subtree']['locations']
    # เรียงตามน้ำหนักมากไปน้อย — คนเปิดดูอยากรู้ว่า "ที่ไหนเยอะ" เป็นอย่างแรก
    assert [(loc['display_name'], loc['totals']['weight_kg']) for loc in locations] == [
        ('ชั้น 1', 50.0),
        ('ศูนย์รับซื้อ สาขาบางนา', 36.0),   # ชั่งที่ตัวอาคารเอง
    ]


def test_locations_sum_back_to_the_branch_total(summary):
    """โครงสร้างรับประกันเอง เพราะมาจากแถวชุดเดียวกัน — เทสนี้กันการรีแฟกเตอร์
    ที่เผลอไปยิง query ใหม่คนละเงื่อนไข"""
    total = sum(loc['totals']['weight_kg'] for loc in summary['subtree']['locations'])
    assert total == summary['subtree']['totals']['weight_kg']


def test_the_own_node_row_is_flagged_so_the_page_can_name_it(summary):
    by_name = {loc['display_name']: loc for loc in summary['subtree']['locations']}
    assert by_name['ศูนย์รับซื้อ สาขาบางนา']['is_self'] is True
    assert by_name['ชั้น 1']['is_self'] is False


def test_a_location_share_is_relative_to_the_branch(summary):
    by_name = {loc['display_name']: loc for loc in summary['subtree']['locations']}
    assert by_name['ชั้น 1']['share_pct'] == 58.1               # 50 / 86
    assert by_name['ศูนย์รับซื้อ สาขาบางนา']['share_pct'] == 41.9  # 36 / 86


def test_a_material_share_under_a_location_is_relative_to_that_location(summary):
    """สองความหมายของ share_pct ในโครงสร้างเดียวกัน ตั้งใจให้ต่างกัน —
    ถ้าเผลอทำให้เหมือนกัน แถบสัดส่วนในกล่องที่ขยายออกมาจะสั้นจู๋ทุกอัน"""
    floor = [loc for loc in summary['subtree']['locations']
             if loc['display_name'] == 'ชั้น 1'][0]
    # ชั้น 1 ชั่ง PET อย่างเดียว 50 กก. → 100% ของตัวเอง แต่ 58.1% ของอาคาร
    assert [m['share_pct'] for m in floor['materials']] == [100.0]
    assert floor['share_pct'] == 58.1


def test_a_leaf_location_still_reports_one_row(session):
    """หน้าเว็บซ่อนกล่องเองเมื่อมีจุดเดียว — service ไม่ต้องรู้เรื่องนั้น"""
    leaf = get_daily_summary(session, 3, 10, date(2026, 7, 26))
    assert len(leaf['subtree']['locations']) == 1
    assert leaf['subtree']['locations'][0]['is_self'] is True


def test_a_quiet_day_lists_no_locations_at_all(session):
    """อาคาร 20 ชั้นที่ยังไม่มีใครชั่ง ไม่ควรได้รายงานแถว 0 กก. ยี่สิบแถว"""
    quiet = get_daily_summary(session, 1, 10, date(2026, 7, 20))
    assert quiet['subtree']['locations'] == []


def test_public_payload_carries_the_split_without_the_ids(summary):
    public = to_public_payload(summary)
    assert [loc['display_name'] for loc in public['locations']] == [
        'ชั้น 1', 'ศูนย์รับซื้อ สาขาบางนา',
    ]
    for loc in public['locations']:
        assert 'origin_id' not in loc
        for entry in loc['materials']:
            assert 'material_id' not in entry
            assert 'category_id' not in entry


def test_the_split_is_json_serialisable(summary):
    """Decimal จาก Postgres ต้องถูกแปลงในชั้นที่ซ้อนอยู่ด้วย ไม่ใช่แค่ชั้นบน"""
    json.dumps(to_public_payload(summary))
