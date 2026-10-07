"""Global "Send emails" switch — settings registry + the gate every email passes."""
import pytest

from GEPPPlatform.services.settings import email_gate, global_settings as gs


def _msg(*emails):
    return {'subject': 'Hi', 'html': '<p>x</p>', 'to': [{'email': e, 'type': 'to'} for e in emails]}


def test_default_is_on_only_on_prod_lambdas(monkeypatch):
    monkeypatch.setenv('AWS_LAMBDA_FUNCTION_NAME', 'PROD-GEPPPlatform-AUDITCRON')
    assert gs.running_in_production()
    monkeypatch.setenv('AWS_LAMBDA_FUNCTION_NAME', 'DEV-GEPPPlatform')
    assert not gs.running_in_production()
    monkeypatch.delenv('AWS_LAMBDA_FUNCTION_NAME', raising=False)   # local server
    assert not gs.running_in_production()


def test_env_override_beats_the_name(monkeypatch):
    monkeypatch.setenv('AWS_LAMBDA_FUNCTION_NAME', 'DEV-GEPPPlatform')
    monkeypatch.setenv('EMAIL_SENDING_DEFAULT', 'on')
    assert gs._email_default() is True
    monkeypatch.setenv('AWS_LAMBDA_FUNCTION_NAME', 'PROD-GEPPPlatform')
    monkeypatch.setenv('EMAIL_SENDING_DEFAULT', 'off')
    assert gs._email_default() is False
    monkeypatch.delenv('EMAIL_SENDING_DEFAULT')
    assert gs._email_default() is True


def test_recipient_list_coercion():
    assert gs._as_recipient_list('Top@GEPP.me, @gepp.me\nnot-an-entry  x@y\n@gepp.me') == ['top@gepp.me', '@gepp.me']
    assert gs._as_recipient_list(['A@B.co', 'b.co']) == ['a@b.co', 'b.co']
    assert gs._as_recipient_list(None) == []
    spec = gs.REGISTRY[gs.NOTIFICATION_EMAIL_TEST_RECIPIENTS]
    assert spec.value_type == 'string_list' and spec.section == 'notification'


@pytest.mark.parametrize('email,allow,ok', [
    ('a@gepp.me', ['@gepp.me'], True),
    ('a@gepp.me', ['gepp.me'], True),
    ('a@sub.gepp.me', ['@gepp.me'], False),
    ('top@gepp.me', ['top@gepp.me'], True),
    ('other@gepp.me', ['top@gepp.me'], False),
    ('', ['@gepp.me'], False),
])
def test_recipient_allowed(email, allow, ok):
    assert email_gate.recipient_allowed(email, allow) is ok


def test_switch_on_sends_unchanged(monkeypatch):
    monkeypatch.setattr(email_gate, '_settings', lambda db=None: (True, []))
    m = _msg('customer@example.com')
    assert email_gate.gate_email_message(m) is m


def test_switch_off_keeps_only_test_recipients(monkeypatch):
    monkeypatch.setattr(email_gate, '_settings', lambda db=None: (False, ['@gepp.me']))
    out = email_gate.gate_email_message(_msg('customer@example.com', 'qa@gepp.me'))
    assert [r['email'] for r in out['to']] == ['qa@gepp.me']


def test_switch_off_without_testers_sends_nothing(monkeypatch):
    monkeypatch.setattr(email_gate, '_settings', lambda db=None: (False, []))
    assert email_gate.gate_email_message(_msg('customer@example.com')) is None


def test_unreadable_settings_fall_back_to_the_code_default(monkeypatch):
    def boom(db=None):
        raise RuntimeError('db down')
    monkeypatch.setattr(gs, 'get_all', boom)
    monkeypatch.setattr(gs, '_cache_valid', lambda: True)
    enabled, allow = email_gate._settings()
    assert enabled is bool(gs.REGISTRY[gs.NOTIFICATION_EMAIL_ENABLED].default) and allow == []


def test_email_lambda_follows_the_caller_stage(monkeypatch):
    monkeypatch.delenv('EMAIL_LAMBDA_FUNCTION', raising=False)
    monkeypatch.setenv('AWS_LAMBDA_FUNCTION_NAME', 'DEV-GEPPPlatform')
    assert email_gate.email_lambda_function() == 'DEV-GEPPEmailNotification'
    monkeypatch.setenv('AWS_LAMBDA_FUNCTION_NAME', 'PROD-GEPPPlatform')
    assert email_gate.email_lambda_function() == 'PROD-GEPPEmailNotification'
    monkeypatch.delenv('AWS_LAMBDA_FUNCTION_NAME')            # local server: unchanged default
    assert email_gate.email_lambda_function() == 'PROD-GEPPEmailNotification'
    monkeypatch.setenv('AWS_LAMBDA_FUNCTION_NAME', 'DEV-GEPPPlatform')
    monkeypatch.setenv('EMAIL_LAMBDA_FUNCTION', 'Some-Other-Fn')   # explicit env still wins
    assert email_gate.email_lambda_function() == 'Some-Other-Fn'


def test_skips_are_logged_at_warning_without_full_addresses(monkeypatch, caplog):
    monkeypatch.setattr(email_gate, '_settings', lambda db=None: (False, ['@gepp.me']))
    with caplog.at_level('WARNING', logger=email_gate.logger.name):
        assert email_gate.gate_email_message(_msg('customer@example.com')) is None
    warn = [r.getMessage() for r in caplog.records if r.levelname == 'WARNING']
    assert len(warn) == 1 and 'example.com' in warn[0] and 'nothing sent' in warn[0]
    assert 'customer@' not in warn[0]
