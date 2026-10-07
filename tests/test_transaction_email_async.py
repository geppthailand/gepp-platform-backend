"""Transaction emails are queued (async Lambda invoke) so create/approve don't wait on Mailchimp."""
import io
import json

from GEPPPlatform.services.cores.transactions import transaction_service as ts
from GEPPPlatform.services.settings import email_gate


class _FakeLambda:
    def __init__(self):
        self.calls = []

    def invoke(self, **kw):
        self.calls.append(kw)
        if kw['InvocationType'] == 'Event':
            return {'StatusCode': 202}
        body = json.dumps({'data': {'status': 'success'}})
        return {'StatusCode': 200, 'Payload': io.BytesIO(json.dumps({'body': body}).encode())}


def _svc(monkeypatch):
    fake = _FakeLambda()
    monkeypatch.setattr(ts, '_get_email_lambda_client', lambda: fake)
    monkeypatch.setattr(email_gate, 'gate_email_message', lambda m, db=None: m)
    monkeypatch.setenv('EMAIL_LAMBDA_FUNCTION', 'DEV-GEPPEmailNotification')
    return ts.TransactionService.__new__(ts.TransactionService), fake


def test_normal_email_is_queued_not_awaited(monkeypatch):
    svc, fake = _svc(monkeypatch)
    assert svc._do_send_email_via_lambda('a@gepp.me', 'Hi', '<p>x</p>') is True
    assert [c['InvocationType'] for c in fake.calls] == ['Event']
    assert fake.calls[0]['FunctionName'] == 'DEV-GEPPEmailNotification'


def test_oversized_payload_falls_back_to_a_synchronous_call(monkeypatch):
    svc, fake = _svc(monkeypatch)
    big = '<p>' + 'x' * (ts._EMAIL_ASYNC_MAX_PAYLOAD + 10) + '</p>'
    assert svc._do_send_email_via_lambda('a@gepp.me', 'Hi', big) is True
    assert [c['InvocationType'] for c in fake.calls] == ['RequestResponse']


def test_gated_email_is_not_invoked(monkeypatch):
    svc, fake = _svc(monkeypatch)
    monkeypatch.setattr(email_gate, 'gate_email_message', lambda m, db=None: None)
    assert svc._do_send_email_via_lambda('customer@example.com', 'Hi', '<p>x</p>') is False
    assert fake.calls == []
