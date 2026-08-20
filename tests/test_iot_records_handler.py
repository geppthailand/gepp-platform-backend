import pytest

from GEPPPlatform.libs.exceptions import APIException
from GEPPPlatform.services.cores.iot_devices import iot_devices_handlers as handlers


def _records_event():
    return {"rawPath": "/api/iot-devices/records"}


def test_iot_records_requires_user_token_context():
    with pytest.raises(APIException) as exc:
        handlers.handle_iot_devices_routes(
            _records_event(),
            data={"data": {"origin_id": 1, "records": []}},
            db_session=None,
            method="POST",
            current_device={"device_id": 1},
            current_user={},
        )

    assert exc.value.status_code == 401
    assert exc.value.error_code == "UNAUTHORIZED"
    assert "user_token" in exc.value.message


class _FakeQuery:
    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return (10,)


class _FakeDb:
    def query(self, *args, **kwargs):
        return _FakeQuery()


def test_iot_records_preserves_api_exception_status(monkeypatch):
    def raise_api_exception(*args, **kwargs):
        raise APIException("transaction boundary failed", status_code=418, error_code="TEAPOT")

    monkeypatch.setattr(handlers, "handle_create_transaction", raise_api_exception)

    with pytest.raises(APIException) as exc:
        handlers.handle_iot_devices_routes(
            _records_event(),
            data={"data": {"origin_id": 1, "records": []}},
            db_session=_FakeDb(),
            method="POST",
            current_device={"device_id": 1},
            current_user={"user_id": 5, "organization_id": 10},
        )

    assert exc.value.status_code == 418
    assert exc.value.error_code == "TEAPOT"
    assert exc.value.message == "transaction boundary failed"


# ─────────────────────────────────────────────────────────────────────
# Auto-approval on save (org switch + per-device override).
#
# These drive the REAL resolver against a fake DB, so the SQL-shape
# assumptions in auto_approve.py are exercised too — not just the branch
# logic in the route.
# ─────────────────────────────────────────────────────────────────────


class _AutoApproveDb(_FakeDb):
    """Answers the column-only SELECTs the route's resolvers make.

    Routed by SQL content rather than a single canned answer: the route now asks
    three different questions (device override, org flag, sorter binding) and a
    fake that says "yes" to all of them tests nothing.
    """

    def __init__(self, device_mode=None, org_flag=False, sorter_location_id=None,
                 destinations=(), member_of=None):
        self.device_mode = device_mode
        self.org_flag = org_flag
        self.sorter_location_id = sorter_location_id
        self.destinations = list(destinations)
        # Destinations this sorter is a MEMBER of — the permission that decides
        # what the picker offers and what the write check accepts. Defaults to
        # every offered destination, so tests about the payload rewrite stay
        # about the payload rewrite; the scoping itself is pinned separately in
        # test_sorter_destination_scope.py and by the route test below.
        self.member_of = list(self.destinations if member_of is None else member_of)

    def execute(self, statement, params=None):
        sql = str(statement)
        if "jsonb_array_elements(members)" in sql:
            return _FakeRows([(d,) for d in self.member_of])
        if "sorter_location_id" in sql:
            return _FakeResult((self.sorter_location_id,) if self.sorter_location_id else None)
        if "type = 'hub'" in sql or "id = ANY" in sql:
            return _FakeRows([(d, f"Destination {d}") for d in self.destinations])
        if "organization_setup" in sql:
            return _FakeResult(([],))
        if "iot_devices" in sql:
            return _FakeResult((self.device_mode,))
        return _FakeResult((self.org_flag,))

    def begin_nested(self):
        raise RuntimeError("no savepoints in tests")  # CRM emit degrades to a no-op


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeRows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _CapturingTransactionService:
    """Stands in for TransactionService; records the auto-approval call."""

    last = None

    def __init__(self, db):
        self.db = db
        self.auto_approvals = []
        _CapturingTransactionService.last = self

    def record_auto_approval(self, **kwargs):
        self.auto_approvals.append(kwargs)


def _run_records_route(monkeypatch, db, payload=None):
    """POST /api/iot-devices/records, returning the payload as create saw it."""
    seen = {}

    def fake_create(service, data, user_id, organization_id, trusted_channel=None):
        seen["data"] = data
        seen["trusted_channel"] = trusted_channel
        return {"success": True, "transaction": {"id": 4242}}

    monkeypatch.setattr(handlers, "handle_create_transaction", fake_create)
    monkeypatch.setattr(handlers, "TransactionService", _CapturingTransactionService)

    data = payload or {"origin_id": 1, "records": [{"material_id": 7}]}
    handlers.handle_iot_devices_routes(
        _records_event(),
        data={"data": data},
        db_session=db,
        method="POST",
        current_device={"device_id": 3},
        current_user={"user_id": 5, "organization_id": 10},
    )
    return seen["data"], _CapturingTransactionService.last, seen.get("trusted_channel")


def test_records_stay_pending_when_auto_approve_is_off(monkeypatch):
    """Default for every existing org: nothing about the payload changes."""
    data, service, _channel = _run_records_route(monkeypatch, _AutoApproveDb(org_flag=False))

    assert "status" not in data
    assert "approved_by_id" not in data
    assert data["records"][0].get("status") is None
    assert service.auto_approvals == []


def test_org_flag_approves_transaction_and_records(monkeypatch):
    data, service, _channel = _run_records_route(monkeypatch, _AutoApproveDb(org_flag=True))

    assert data["status"] == "approved"
    # Both levels — the records drive the audit inbox and the UI status column.
    assert data["records"][0]["status"] == "approved"
    # Approver is the operator who confirmed the weight on the tablet.
    assert data["approved_by_id"] == 5

    assert len(service.auto_approvals) == 1
    call = service.auto_approvals[0]
    assert call["transaction_id"] == 4242
    assert call["actor_user_location_id"] == 5
    assert call["flag_source"] == "org"
    assert call["device_id"] == 3


def test_device_override_off_beats_enabled_org(monkeypatch):
    """One misbehaving scale can be pulled out without touching the org."""
    data, service, _channel = _run_records_route(
        monkeypatch, _AutoApproveDb(device_mode="off", org_flag=True)
    )

    assert "status" not in data
    assert service.auto_approvals == []


def test_device_override_on_beats_disabled_org(monkeypatch):
    """...and a single scale can be piloted the same way."""
    data, service, _channel = _run_records_route(
        monkeypatch, _AutoApproveDb(device_mode="on", org_flag=False)
    )

    assert data["status"] == "approved"
    assert service.auto_approvals[0]["flag_source"] == "device"


# ─────────────────────────────────────────────────────────────────────
# The audit trail written for a machine approval.
# ─────────────────────────────────────────────────────────────────────


class _FakeTxn:
    def __init__(self):
        self.id = 4242
        self.organization_id = 10
        self.notes = "Weighed at station A"
        self.ai_audit_status = None


class _AuditDb:
    def __init__(self, txn):
        self.txn = txn
        self.added = []
        self.commits = 0

    def query(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.txn

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def begin_nested(self):
        raise RuntimeError("no savepoints in tests")


def _record_auto_approval(txn=None):
    from GEPPPlatform.services.cores.transactions.transaction_service import TransactionService

    txn = txn or _FakeTxn()
    db = _AuditDb(txn)
    TransactionService(db).record_auto_approval(
        transaction_id=4242,
        actor_user_location_id=5,
        flag_source="org",
        device_id=3,
    )
    return db, txn


def _added_of_type(db, type_name):
    return [o for o in db.added if type(o).__name__ == type_name]


def test_auto_approval_writes_machine_audit_row():
    db, txn = _record_auto_approval()

    assert db.commits == 1
    audits = _added_of_type(db, "TransactionAudit")
    assert len(audits) == 1
    audit = audits[0]

    assert audit.transaction_id == 4242
    assert audit.audit_type == "auto_scale"
    assert audit.audit_status == "approved"
    assert audit.auditor_id == 5
    assert audit.organization_id == 10
    # A machine decision must never be logged as a human review, and must stay
    # eligible for the AI audit that runs later.
    assert audit.by_human is False
    assert audit.ai_audit_status == "null"
    assert audit.audit_notes["s"] == "approved"
    assert audit.audit_notes["v"] == []
    assert audit.audit_notes["flag_source"] == "org"
    assert audit.audit_notes["device_id"] == 3


def test_auto_approval_emits_transaction_approved_event():
    """create-as-approved never passes through update_transaction, so this path
    has to emit the CRM event itself or every scale reading misses it."""
    db, _ = _record_auto_approval()

    events = _added_of_type(db, "CrmEvent")
    assert [e.event_type for e in events] == ["transaction_approved"]


def test_auto_approval_appends_note_without_losing_existing_notes():
    db, txn = _record_auto_approval()

    assert txn.notes.startswith("Weighed at station A")
    assert "Auto-approved on save" in txn.notes
    assert "device #3" in txn.notes
    assert "flag source: org" in txn.notes


def test_auto_approval_survives_a_missing_transaction():
    """Best-effort: the operator already saved the weighing — never raise."""
    db = _AuditDb(txn=None)
    from GEPPPlatform.services.cores.transactions.transaction_service import TransactionService

    TransactionService(db).record_auto_approval(
        transaction_id=999, actor_user_location_id=5, flag_source="device", device_id=3
    )
    assert db.added == []


# ─────────────────────────────────────────────────────────────────────
# Provenance shown in the transaction list: channel + who approved.
# ─────────────────────────────────────────────────────────────────────


def test_scale_payload_is_stamped_as_iot(monkeypatch):
    """The tablet posts 'manual_input'/'origin' — the server has to correct both, or a
    weighing is indistinguishable from something typed on the web."""
    payload = {'origin_id': 1, 'records': [{'material_id': 7, 'transaction_type': 'manual_input'}]}
    data, _, _channel = _run_records_route(monkeypatch, _AutoApproveDb(org_flag=False), payload=payload)

    assert data['transaction_method'] == 'scale_input'
    assert data['records'][0]['transaction_type'] == 'iot'


def test_source_is_stamped_even_when_auto_approve_is_off(monkeypatch):
    """Channel and approval are independent: turning auto-approval off must not make
    scale rows anonymous again."""
    data, service, _channel = _run_records_route(monkeypatch, _AutoApproveDb(org_flag=False))

    assert data['transaction_method'] == 'scale_input'
    assert 'status' not in data
    assert service.auto_approvals == []


class _Txn:
    def __init__(self, **kw):
        self.transaction_method = kw.get('method', 'origin')
        self.import_file_id = kw.get('import_file_id')
        self.status = kw.get('status', 'pending')
        self.is_user_audit = kw.get('is_user_audit', False)
        self.ai_audit_status = kw.get('ai_audit_status', 'null')


def _svc():
    from GEPPPlatform.services.cores.transactions.transaction_service import TransactionService
    return TransactionService(db=None)


@pytest.mark.parametrize("kwargs,expected", [
    ({'method': 'scale_input'}, 'iot'),
    ({'method': 'qr_input'}, 'qr_input'),
    ({'method': 'origin', 'import_file_id': 12}, 'import'),
    ({'method': 'origin'}, 'manual'),
    ({'method': None}, 'manual'),
])
def test_transaction_source(kwargs, expected):
    assert _svc()._transaction_source(_Txn(**kwargs)) == expected


@pytest.mark.parametrize("kwargs,auto,expected", [
    # Undecided rows carry no approver.
    ({'status': 'pending'}, True, None),
    # A machine approval, untouched since.
    ({'status': 'approved'}, True, 'auto_scale'),
    # A human reviewed it afterwards — the human wins.
    ({'status': 'approved', 'is_user_audit': True}, True, 'human'),
    # The AI ruled on it afterwards — the AI wins over the machine approval.
    ({'status': 'rejected', 'ai_audit_status': 'rejected'}, True, 'ai'),
    ({'status': 'approved', 'ai_audit_status': 'approved'}, True, 'ai'),
    # Approved through the plain status-update endpoint: still a person.
    ({'status': 'approved'}, False, 'human'),
])
def test_approval_source_precedence(kwargs, auto, expected):
    assert _svc()._approval_source(_Txn(**kwargs), auto) == expected


# ─────────────────────────────────────────────────────────────────────
# ผู้คัดแยก (sorter) mode: the same POST means the opposite thing.
# ─────────────────────────────────────────────────────────────────────


WASTE_ROOM = 77
SCRAP_DEALER = 501


def _sorter_db(**kw):
    kw.setdefault("sorter_location_id", WASTE_ROOM)
    kw.setdefault("destinations", [SCRAP_DEALER, 502])
    return _AutoApproveDb(**kw)


def test_sorter_post_is_read_the_other_way_round(monkeypatch):
    """The tablet was offered destinations, so the id it posted is where the
    material WENT — the origin is the sorter's own waste room."""
    payload = {"origin_id": SCRAP_DEALER, "records": [{"material_id": 7}]}
    data, _, _channel = _run_records_route(monkeypatch, _sorter_db(), payload=payload)

    assert data["origin_id"] == WASTE_ROOM
    assert data["records"][0]["destination_id"] == SCRAP_DEALER


def test_sorter_post_is_marked_as_an_internal_transfer(monkeypatch):
    """These kilograms were already weighed in from the tenant that produced them.

    The records have to exist — a traceability pile's weight comes only from its
    records — so the double count is prevented by labelling the weighing instead,
    and the reports leave labelled rows out of waste-generated totals.
    """
    payload = {"origin_id": SCRAP_DEALER, "records": [{"material_id": 7}]}
    data, _, _channel = _run_records_route(monkeypatch, _sorter_db(), payload=payload)

    assert data["is_internal_transfer"] is True


def test_a_normal_weighing_is_not_an_internal_transfer(monkeypatch):
    """The weigher records material arriving from a tenant — that IS generation.

    Absence matters as much as presence here: mark this one and an organization's
    reported tonnage silently drops to zero.
    """
    data, _, _channel = _run_records_route(monkeypatch, _AutoApproveDb(org_flag=False))

    assert data.get("is_internal_transfer") is not True


def test_sorter_post_records_provenance(monkeypatch):
    """A server-substituted origin must be identifiable afterwards — the payload
    alone no longer explains what happened."""
    payload = {"origin_id": SCRAP_DEALER, "records": [{"material_id": 7}]}
    data, _, _channel = _run_records_route(monkeypatch, _sorter_db(), payload=payload)

    assert f"Sorted at #{WASTE_ROOM}" in data["notes"]
    assert f"destination #{SCRAP_DEALER}" in data["notes"]


def test_sorter_cannot_post_to_a_destination_never_offered(monkeypatch):
    """Nothing downstream validates destination_id, so this is the only gate.

    Asserts that the write never happened, rather than which exception came out:
    sibling test modules replace APIException with a stub that takes no keyword
    arguments, so anything asserting on the exception itself is testing the test
    suite's import order (which is why the two oldest tests in this file fail in
    a full run). "The transaction was not created" is the behaviour that matters.
    """
    reached_create = []

    def fake_create(service, data, user_id, organization_id, trusted_channel=None):
        reached_create.append(data)
        return {"success": True, "transaction": {"id": 4242}}

    monkeypatch.setattr(handlers, "handle_create_transaction", fake_create)
    monkeypatch.setattr(handlers, "TransactionService", _CapturingTransactionService)

    try:
        handlers.handle_iot_devices_routes(
            _records_event(),
            data={"data": {"origin_id": 999999, "records": [{"material_id": 7}]}},
            db_session=_sorter_db(),
            method="POST",
            current_device={"device_id": 3},
            current_user={"user_id": 5, "organization_id": 10},
        )
    except Exception:  # noqa: BLE001 — class identity is not what is under test
        pass

    assert reached_create == [], "a destination that was never offered must not be written"


def test_sorter_stamping_still_marks_the_row_as_scale_sourced(monkeypatch):
    payload = {"origin_id": SCRAP_DEALER, "records": [{"material_id": 7}]}
    data, _, _channel = _run_records_route(monkeypatch, _sorter_db(), payload=payload)

    assert data["transaction_method"] == "scale_input"
    assert data["records"][0]["transaction_type"] == "iot"


def test_weigher_payload_is_untouched_when_there_is_no_binding(monkeypatch):
    """Regression: everyone without a binding must behave exactly as before."""
    payload = {"origin_id": 2445, "records": [{"material_id": 7}]}
    data, _, _channel = _run_records_route(
        monkeypatch, _AutoApproveDb(sorter_location_id=None), payload=payload
    )

    assert data["origin_id"] == 2445
    assert data["records"][0].get("destination_id") is None
    assert "notes" not in data


# ─────────────────────────────────────────────────────────────────────
# Channel markers (migration 086).
#
# transaction_method='scale_input' and is_internal_transfer stopped being
# labels the day the tank model shipped: they now decide which piles are
# per-weighing, which locations become collection points, whose kilograms
# get superseded in the recycling rate, and what a tank's balance says.
# The server stamps them from facts it can verify; a client must not be
# able to assert them. These pin the trust boundary at the route.
# ─────────────────────────────────────────────────────────────────────


def test_the_scale_route_declares_itself_the_trusted_channel(monkeypatch):
    """Without this the create handler strips the very markers the route
    just stamped, and every weighing degrades to an ordinary web entry."""
    _data, _service, channel = _run_records_route(
        monkeypatch, _AutoApproveDb(org_flag=False)
    )
    assert channel == "iot"


def test_the_trusted_channel_is_declared_for_a_sorter_too(monkeypatch):
    """The weigh-out carries is_internal_transfer, which is what keeps its
    kilograms out of "waste generated" and inside the tank's outflow."""
    payload = {"origin_id": SCRAP_DEALER, "records": [{"material_id": 7}]}
    data, _service, channel = _run_records_route(
        monkeypatch, _sorter_db(), payload=payload
    )
    assert channel == "iot"
    assert data["is_internal_transfer"] is True


# ─────────────────────────────────────────────────────────────────────
# The weigh-out is a TRACEABILITY act, not a waste intake.
#
# The material was already reviewed when it was weighed IN; this row only
# records where it went. So it is always stored approved — no switch can
# park it as pending — and it is hidden from the transaction list (see
# list_transactions) and never swept into the AI audit. A pending or
# AI-rejected weigh-out would be invisible everywhere a human looks,
# holding the tank's outbound legs hostage to a review nobody can perform.
# ─────────────────────────────────────────────────────────────────────


def test_sorter_weigh_out_is_approved_even_with_every_switch_off(monkeypatch):
    """Device override unset, org flag off — the exact configuration that
    parks a normal weighing as pending must still approve a weigh-out."""
    payload = {"origin_id": SCRAP_DEALER, "records": [{"material_id": 7}]}
    data, _, _channel = _run_records_route(
        monkeypatch, _sorter_db(device_mode=None, org_flag=False), payload=payload
    )

    assert data["status"] == "approved"
    assert data["records"][0]["status"] == "approved"


def test_sorter_forced_approval_is_attributed_to_the_binding(monkeypatch):
    """The audit note must say WHY this was machine-approved: 'sorter', not a
    device or org switch that was in fact off."""
    payload = {"origin_id": SCRAP_DEALER, "records": [{"material_id": 7}]}
    _data, service, _channel = _run_records_route(
        monkeypatch, _sorter_db(device_mode=None, org_flag=False), payload=payload
    )

    assert len(service.auto_approvals) == 1
    assert service.auto_approvals[0]["flag_source"] == "sorter"


def test_a_device_switched_OFF_cannot_park_a_weigh_out_as_pending(monkeypatch):
    """The per-device kill switch beats the org flag for weigh-INS; the
    weigh-out is not that fight — it must approve regardless."""
    payload = {"origin_id": SCRAP_DEALER, "records": [{"material_id": 7}]}
    data, _, _channel = _run_records_route(
        monkeypatch, _sorter_db(device_mode="off", org_flag=True), payload=payload
    )

    assert data["status"] == "approved"


def test_a_normal_weighing_still_obeys_the_switches(monkeypatch):
    """Regression: the forced approval is scoped to the sorter binding —
    a weigher's intake with everything off must stay pending for review."""
    data, service, _channel = _run_records_route(
        monkeypatch, _AutoApproveDb(device_mode=None, org_flag=False)
    )

    assert data.get("status") != "approved"
    assert service.auto_approvals == []


def test_a_sorter_cannot_post_to_a_destination_they_do_not_belong_to(monkeypatch):
    """Membership on the destination is the permission, and the WRITE path has to
    enforce it — not just the picker. Narrowing the picker alone would leave the
    API accepting every destination in the organisation while the tablet showed
    one, which is a hole rather than a restriction.

    Asserts the write never happened rather than which exception surfaced: sibling
    modules stub APIException, so asserting on the class tests the import order.
    """
    reached_create = []

    def fake_create(service, data, user_id, organization_id, trusted_channel=None):
        reached_create.append(data)
        return {"success": True, "transaction": {"id": 4242}}

    monkeypatch.setattr(handlers, "handle_create_transaction", fake_create)
    monkeypatch.setattr(handlers, "TransactionService", _CapturingTransactionService)

    # The dealer is offered by the organisation but this sorter belongs to 502.
    db = _AutoApproveDb(
        sorter_location_id=WASTE_ROOM,
        destinations=[SCRAP_DEALER, 502],
        member_of=[502],
    )
    try:
        handlers.handle_iot_devices_routes(
            _records_event(),
            data={"data": {"origin_id": SCRAP_DEALER, "records": [{"material_id": 7}]}},
            db_session=db,
            method="POST",
            current_device={"device_id": 3},
            current_user={"user_id": 5, "organization_id": 10},
        )
    except Exception:  # noqa: BLE001 — class identity is not what is under test
        pass

    assert reached_create == [], "a destination the sorter does not belong to must not be written"


def test_a_sorter_can_still_post_to_a_destination_they_belong_to(monkeypatch):
    """The counterweight: the guard must not lock out the legitimate case."""
    db = _AutoApproveDb(
        sorter_location_id=WASTE_ROOM,
        destinations=[SCRAP_DEALER, 502],
        member_of=[SCRAP_DEALER],
    )
    payload = {"origin_id": SCRAP_DEALER, "records": [{"material_id": 7}]}
    data, _, _channel = _run_records_route(monkeypatch, db, payload=payload)

    assert data["origin_id"] == WASTE_ROOM
    assert data["records"][0]["destination_id"] == SCRAP_DEALER
