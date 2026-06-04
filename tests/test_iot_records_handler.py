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
