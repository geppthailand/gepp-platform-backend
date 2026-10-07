"""Scheduled report: one email, Thai first then English, with a TH and an EN PDF attached."""
from datetime import datetime

from GEPPPlatform.services.cores.reports import schedule_report as sr

MON = datetime(2026, 10, 5, 8, 0, tzinfo=sr.THAI_TZ)      # a Monday, 1st-of-month logic not involved


def test_thai_period_matches_the_english_period():
    assert sr.get_report_period_display_th('RPT_TXN_WEEKLY', MON) == 'รายสัปดาห์ (28 กันยายน 2569 – 4 ตุลาคม 2569)'
    assert sr.get_report_period_display('RPT_TXN_WEEKLY', MON)[0] == 'Weekly - (28 September 2026 - 4 October 2026)'
    assert sr.get_report_period_display_th('RPT_TXN_MONTHLY', datetime(2026, 10, 1, 8, tzinfo=sr.THAI_TZ)) == 'รายเดือน (กันยายน 2569)'
    assert sr.get_report_period_display_th('RPT_TXN_DAILY', MON, '08:00') == 'รายวัน (5 ตุลาคม 2569 00:00 – 08:00 น.)'


def test_filenames_get_a_language_suffix():
    assert sr._lang_filename('report_2026-09-28_2026-10-04.pdf', 'th') == 'report_2026-09-28_2026-10-04_TH.pdf'
    assert sr._lang_filename('report', 'en') == 'report_EN.pdf'


def test_email_puts_thai_above_english():
    subject, html, text = sr.build_scheduled_report_email(
        'รายสัปดาห์ (…)', 'Weekly - (…)', [('th', 'r_TH.pdf'), ('en', 'r_EN.pdf')])
    assert subject.startswith('รายงานตามกำหนดเวลา / Scheduled Report')
    assert html.index('lang="th"') < html.index('lang="en"')
    assert html.index('เรียน ผู้ใช้งาน') < html.index('Hello,')
    assert 'r_TH.pdf' in html and 'r_EN.pdf' in html
    assert text.index('ไฟล์แนบ') < text.index('Attachments')


def _job(monkeypatch, time_left=None, fail_lang=None):
    settings = [{'id': 1, 'organization_id': 10, 'event': 'RPT_TXN_WEEKLY', 'role_id': 5, 'channels_mask': 1, 'email_time': '08:00'},
                {'id': 2, 'organization_id': 11, 'event': 'RPT_TXN_WEEKLY', 'role_id': 6, 'channels_mask': 1, 'email_time': '08:00'}]
    monkeypatch.setattr(sr, 'get_scheduled_settings_for_current_hour', lambda db: settings)
    class _Now(datetime):
        @classmethod
        def now(cls, tz=None):
            return MON
    monkeypatch.setattr(sr, 'datetime', _Now)
    monkeypatch.setattr(sr, 'get_user_emails_by_org_and_role', lambda db, o, r: ['a@x.co', 'b@x.co'])
    monkeypatch.setattr(sr, 'get_one_user_context_for_org_role', lambda db, o, r: {'id': 1, 'timezone': 'Asia/Bangkok'})
    calls, sent = [], []

    def fake_export(svc, org, filters, user, language='en'):
        calls.append((org, language))
        if language == fail_lang:
            return {'success': False}
        return {'statusCode': 200, 'body': f'PDF-{language}', 'headers': {'Content-Disposition': 'attachment; filename="rep.pdf"'}}

    import GEPPPlatform.services.cores.reports.reports_handlers as rh
    import GEPPPlatform.services.cores.reports.reports_service as rs
    monkeypatch.setattr(rh, '_handle_export_pdf_report', fake_export)
    monkeypatch.setattr(rs, 'ReportsService', lambda db: object())
    monkeypatch.setattr(sr.boto3, 'client', lambda *a, **k: object())
    monkeypatch.setattr(sr, '_send_email_via_lambda',
                        lambda to, subj, html, text, attachments=None, lambda_client=None: sent.append((to, [a['name'] for a in attachments])) or True)
    result = sr.run_scheduled_report_job(db=None, time_left_ms=time_left)
    return result, calls, sent


def test_each_setting_exports_both_languages_and_attaches_both(monkeypatch):
    result, calls, sent = _job(monkeypatch)
    assert calls == [(10, 'th'), (10, 'en'), (11, 'th'), (11, 'en')]
    assert len(sent) == 4 and all(files == ['rep_TH.pdf', 'rep_EN.pdf'] for _, files in sent)
    assert result['exports'][0]['export_success'] == {'th': True, 'en': True, 'sent': 2}


def test_a_failed_language_still_sends_the_other(monkeypatch):
    _, _, sent = _job(monkeypatch, fail_lang='th')
    assert len(sent) == 4 and all(files == ['rep_EN.pdf'] for _, files in sent)


def test_stops_starting_settings_when_out_of_time(monkeypatch):
    left = iter([60_000, 1_000])          # enough for the first org, not the second
    result, calls, sent = _job(monkeypatch, time_left=lambda: next(left))
    assert {org for org, _ in calls} == {10}
    assert len(result['exports']) == 1
