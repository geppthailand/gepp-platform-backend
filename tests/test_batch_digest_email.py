"""Approve / Reject All digest: weight summed per waste type, transaction numbers under the table."""
from GEPPPlatform.services.cores.transactions import transaction_service as ts


def _svc():
    return ts.TransactionService.__new__(ts.TransactionService)


MATS = {
    101: [{'name': 'ขยะทั่วไป', 'weight_kg': 10.0}, {'name': 'กระดาษ', 'weight_kg': 2.5}],
    102: [{'name': 'ขยะทั่วไป', 'weight_kg': 5.25}],
    103: [{'name': 'ขยะทั่วไป', 'weight_kg': 1000.0}, {'name': 'ขยะทั่วไป', 'weight_kg': 1.0}],
}


def test_weights_are_summed_per_waste_type(monkeypatch):
    monkeypatch.setenv('WEB_BASE_URL', 'https://dev.geppdata.com/')
    subject, html, text = _svc()._build_batch_digest('approved', 7, [103, 101, 102], MATS)
    assert subject == '3 transactions approved – GEPP Platform'
    # one row per type, biggest first: ขยะทั่วไป 1,016.25 kg over 3 transactions, กระดาษ 2.5 kg over 1
    assert '- ขยะทั่วไป: 3 transactions, 1,016.25 kg' in text
    assert '- กระดาษ: 1 transaction, 2.5 kg' in text
    assert text.index('ขยะทั่วไป') < text.index('กระดาษ')
    assert 'Total: 3 transactions, 1,018.75 kg' in text
    assert 'Transactions (3): #101, #102, #103' in text
    assert html.count('ขยะทั่วไป') == 1          # not repeated per transaction
    assert 'https://dev.geppdata.com/waste-transactions?audit_batch=7&audit_action=approved' in html


def test_long_batches_list_the_first_ids_then_a_count(monkeypatch):
    monkeypatch.delenv('WEB_BASE_URL', raising=False)
    svc = _svc()
    tids = list(range(1, svc.BATCH_EMAIL_MAX_ROWS + 6))
    _, html, text = svc._build_batch_digest('rejected', 9, tids, {})
    assert f'#{svc.BATCH_EMAIL_MAX_ROWS} … and 5 more' in text
    assert f'#{svc.BATCH_EMAIL_MAX_ROWS + 1}' not in text
    assert 'https://geppdata.com/waste-transactions?audit_batch=9&audit_action=rejected' in html


def test_kg_formatting():
    f = ts.TransactionService._fmt_kg
    assert [f(0), f(100), f(1000), f(1234.5), f(0.125)] == ['0', '100', '1,000', '1,234.5', '0.12']
