"""Debug Log Mode → "[DEBUG] Test Scale" on scale intake.

What matters:
  * only weighings posted while the admin's 1-hour window is open are stamped —
    an expired, cleared or unreadable window must never mark real intake;
  * both the transaction and each record are stamped, and the tablet's own
    record note (its device name) survives after the marker;
  * a retried post does not stack the marker.
"""

from datetime import datetime, timedelta, timezone

from GEPPPlatform.services.cores.iot_devices import debug_stamp as D

NOW = datetime(2026, 9, 30, 6, 0, 0, tzinfo=timezone.utc)


def _iso(dt):
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


class FakeSession:
    def __init__(self, value=None, boom=False):
        self.value, self.boom, self.calls = value, boom, []

    def execute(self, stmt, params):
        self.calls.append(params)
        if self.boom:
            raise RuntimeError('db down')
        value = self.value

        class R:
            def fetchone(self_inner):
                return None if value is ... else (value,)
        return R()


def test_active_only_inside_the_window():
    assert D.is_debug_log_active(FakeSession(_iso(NOW + timedelta(minutes=30))), 4, now=NOW)
    assert not D.is_debug_log_active(FakeSession(_iso(NOW - timedelta(seconds=1))), 4, now=NOW)


def test_off_when_cleared_missing_malformed_or_unreadable():
    assert not D.is_debug_log_active(FakeSession(None), 4, now=NOW)       # key removed
    assert not D.is_debug_log_active(FakeSession(...), 4, now=NOW)        # no health row
    assert not D.is_debug_log_active(FakeSession('not-a-date'), 4, now=NOW)
    assert not D.is_debug_log_active(FakeSession(boom=True), 4, now=NOW)
    assert not D.is_debug_log_active(FakeSession(_iso(NOW)), None, now=NOW)


def test_stamps_transaction_and_records_keeping_device_name():
    data = {'notes': '', 'records': [{'notes': 'Scale-Tablet-04'}, {'notes': None}, 'junk']}
    D.stamp_debug_notes(data)
    assert data['notes'] == '[DEBUG] Test Scale'
    assert data['records'][0]['notes'] == '[DEBUG] Test Scale\nScale-Tablet-04'
    assert data['records'][1]['notes'] == '[DEBUG] Test Scale'


def test_stamp_is_idempotent():
    data = {'notes': 'x', 'records': [{'notes': 'Tab'}]}
    D.stamp_debug_notes(data)
    D.stamp_debug_notes(data)
    assert data['notes'] == '[DEBUG] Test Scale\nx'
    assert data['records'][0]['notes'] == '[DEBUG] Test Scale\nTab'
