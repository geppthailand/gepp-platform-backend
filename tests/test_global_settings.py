"""Platform-wide settings — the registry, the defaults, and the failure modes.

What actually matters here is not "can it store a boolean". It is:

  * a MISSING row behaves exactly like a fresh install (code default), so a
    failed seed, a rolled-back migration and a deleted row are indistinguishable;
  * a read NEVER raises, because the subscription gate consults one of these on
    every request and a broken settings table must not decide who can log in;
  * an UNKNOWN key is rejected on write, so a typo cannot silently become a
    setting nothing honours — which presents to an operator as "I turned it off
    and nothing happened";
  * a partial save is impossible, because a settings form that half-applied is
    worse than one that failed.
"""

import json

import pytest

from GEPPPlatform.services.settings import global_settings as gs

KEY = gs.SUBSCRIPTION_DISABLE_WHEN_NOT_IN_PERIOD


@pytest.fixture(autouse=True)
def clean_cache():
    """The cache is module-level state; leaking it between tests hides bugs."""
    gs.invalidate_cache()
    yield
    gs.invalidate_cache()


class FakeDB:
    """Just enough Session to serve `SELECT`/`INSERT` on system_settings."""

    def __init__(self, rows=None, explode=False, audit=True):
        # rows: {key: python value} — stored as JSONB would come back
        self.rows = dict(rows or {})
        self.explode = explode
        self.audit = audit
        self.writes = []
        self.selects = 0

    def execute(self, statement, params=None):
        if self.explode:
            raise RuntimeError('relation "system_settings" does not exist')

        sql = str(statement)
        if sql.strip().upper().startswith('INSERT'):
            self.writes.append(dict(params or {}))
            self.rows[params['key']] = json.loads(params['value'])
            return FakeResult([])

        if 'updated_by' in sql:            # the audit read in describe()
            if not self.audit:
                raise RuntimeError('no such column')
            return FakeResult([(k, 7, None) for k in self.rows])

        self.selects += 1
        return FakeResult(list(self.rows.items()))


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class TestDefaults:
    def test_an_empty_table_yields_the_code_default(self):
        assert gs.get_all(FakeDB())[KEY] is False

    def test_the_gate_ships_off(self):
        # Deliberate: on current data, ON blocks 237 orgs / 224 users / 20 QR
        # forms. A default that locks people out on deploy gets reverted in a
        # panic, so the switch ships off and ops turns it on knowingly.
        assert gs.REGISTRY[KEY].default is False
        assert gs.subscription_gate_enabled(FakeDB()) is False

    def test_a_stored_override_wins(self):
        assert gs.subscription_gate_enabled(FakeDB({KEY: True})) is True

    def test_a_deleted_row_is_the_same_as_never_set(self):
        db = FakeDB({KEY: True})
        assert gs.subscription_gate_enabled(db) is True
        db.rows.clear()
        gs.invalidate_cache()
        assert gs.subscription_gate_enabled(db) is False


class TestNeverRaises:
    def test_a_broken_table_resolves_to_defaults(self):
        # The gate calls this on every request; raising here would be an outage.
        assert gs.get_all(FakeDB(explode=True)) == {KEY: False}

    def test_a_broken_table_does_not_enable_the_gate(self):
        # Direction matters: failing "on" would lock out every customer.
        assert gs.subscription_gate_enabled(FakeDB(explode=True)) is False

    def test_an_unknown_key_reads_as_none_without_raising(self):
        assert gs.get_setting(FakeDB(), 'nope.not_a_setting') is None

    def test_describe_survives_a_missing_audit_column(self):
        doc = gs.describe(FakeDB({KEY: True}, audit=False))
        row = doc['sections'][0]['settings'][0]
        assert row['value'] is True
        assert row['everSet'] is False   # audit unreadable, value still right


class TestCoercion:
    @pytest.mark.parametrize('stored,expect', [
        (True, True), (False, False),
        ('true', True), ('True', True), ('on', True), ('1', True), ('yes', True),
        ('false', False), ('no', False), ('', False),
        (1, True), (0, False),
        (None, False),
        ({'oops': 1}, False),   # a corrupt value must not read as enabled
    ])
    def test_stored_values_coerce_to_a_real_bool(self, stored, expect):
        assert gs.get_all(FakeDB({KEY: stored}))[KEY] is expect

    def test_one_malformed_row_does_not_reset_the_others(self):
        """A row that is not JSON must not abort the whole read.

        It did: `json.loads` was called per row inside one try/except around
        the SELECT, so a single unparseable value sent EVERY setting back to
        its default — silently switching off unrelated features.
        """
        db = FakeDB({KEY: True})
        db.rows['garbage.not_in_registry'] = 'on'   # ignored: not a known key
        assert gs.get_all(db)[KEY] is True

        gs.invalidate_cache()
        db.rows[KEY] = 'on'                          # known key, non-JSON value
        assert gs.get_all(db)[KEY] is True           # coerced, not defaulted

    def test_a_json_string_column_is_parsed(self):
        # Belt and braces: JSONB gives a bool, but a row written as text by
        # something outside this module would arrive as '"true"'.
        db = FakeDB()
        db.rows[KEY] = 'true'
        assert gs.get_all(db)[KEY] is True


class TestWrites:
    def test_set_setting_writes_valid_json_not_python_repr(self):
        db = FakeDB()
        gs.set_setting(db, KEY, True, updated_by=42)
        # `str(True)` is 'True', which is not valid JSON and would break the
        # jsonb cast on the way in.
        assert db.writes[0]['value'] == 'true'
        assert db.writes[0]['updated_by'] == 42

    def test_set_setting_returns_the_coerced_value(self):
        assert gs.set_setting(FakeDB(), KEY, 'yes') is True

    def test_writing_invalidates_the_cache(self):
        db = FakeDB({KEY: False})
        assert gs.subscription_gate_enabled(db) is False
        gs.set_setting(db, KEY, True)
        # Without invalidation this would still read False for 30 seconds —
        # i.e. the operator flips the switch and nothing happens.
        assert gs.subscription_gate_enabled(db) is True

    def test_an_unknown_key_is_rejected(self):
        with pytest.raises(ValueError, match='Unknown global setting'):
            gs.set_setting(FakeDB(), 'subscription.disable_when_not_in_perlod', True)

    def test_set_many_rejects_the_whole_payload_if_any_key_is_unknown(self):
        db = FakeDB()
        with pytest.raises(ValueError):
            gs.set_many(db, {KEY: True, 'bogus.key': 1})
        # Nothing written: a partially-applied settings save is unreadable to
        # the operator, who cannot tell which half took effect.
        assert db.writes == []


class TestCache:
    def test_repeated_reads_hit_the_cache(self):
        db = FakeDB({KEY: True})
        for _ in range(5):
            gs.subscription_gate_enabled(db)
        assert db.selects == 1

    def test_use_cache_false_always_reads(self):
        db = FakeDB({KEY: True})
        gs.get_all(db, use_cache=False)
        gs.get_all(db, use_cache=False)
        assert db.selects == 2

    def test_a_failed_read_is_not_cached(self):
        # Otherwise one blip pins every container to defaults for the full TTL.
        db = FakeDB(explode=True)
        gs.get_all(db)
        db.explode = False
        db.rows[KEY] = True
        assert gs.subscription_gate_enabled(db) is True

    def test_describe_never_serves_a_stale_value(self):
        # The settings PAGE must show what is actually stored, or an operator
        # sees their own save appear not to have happened.
        db = FakeDB({KEY: False})
        gs.get_all(db)
        db.rows[KEY] = True
        assert gs.describe(db)['values'][KEY] is True


class TestDescribeShape:
    def test_settings_are_grouped_by_section_for_the_ui_tabs(self):
        doc = gs.describe(FakeDB())
        sections = {s['section'] for s in doc['sections']}
        assert 'subscription' in sections
        assert all(spec.section for spec in gs.REGISTRY.values())

    def test_is_default_and_ever_set_are_independent(self):
        # A key explicitly set BACK to its default is default-valued AND has
        # been written. Deriving one from the other reported "never changed"
        # on a key somebody had just changed twice.
        db = FakeDB()
        gs.set_setting(db, KEY, False, updated_by=1)
        row = gs.describe(db)['sections'][0]['settings'][0]
        assert row['isDefault'] is True
        assert row['everSet'] is True

    def test_every_registry_entry_has_operator_facing_prose(self):
        # These strings ARE the UI. A switch with no explanation of what
        # happens when it is on is a switch nobody dares touch.
        for key, spec in gs.REGISTRY.items():
            assert spec.label, key
            assert len(spec.help_text) > 40, key
