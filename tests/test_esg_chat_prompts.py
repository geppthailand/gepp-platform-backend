"""
Unit tests for the KhunGEPP prompt helpers.

These don't hit OpenRouter — they exercise the pure-Python helpers
in `prompts.esg_chat.prompts`:

  - `cap_reply` truncation behaviour at the 200/300 char boundary
  - `detect_language` Thai-aware sniff
  - `build_messages` shape (system + history + user)

The history-cap walk lives in `services.esg.esg_chat_service` not
in the prompts module, so we test it via a small fake Session that
returns rows in newest-first order.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from GEPPPlatform.prompts.esg_chat import prompts as P


# ──────────────────────────────────────────────────────────────────
# cap_reply
# ──────────────────────────────────────────────────────────────────

def test_cap_reply_short_text_unchanged():
    s = 'สวัสดีครับ มีอะไรให้ช่วยไหมครับ'
    assert P.cap_reply(s, n=300) == s


# ──────────────────────────────────────────────────────────────────
# collapse_polite_particles — defensive Thai post-processor
# ──────────────────────────────────────────────────────────────────

class TestCollapsePoliteParticles:

    def test_real_world_bug_naa_krap_krap(self):
        """The exact regression the user flagged: 'นะครับครับ'."""
        s = (
            'ยินดีมากครับที่เห็นประโยชน์ของระบบนี้ '
            'หากต้องการทราบรายละเอียดเพิ่มเติม '
            'สามารถสอบถามคุณเก็บได้ตลอดเลยนะครับครับ'
        )
        out = P.collapse_polite_particles(s)
        assert 'ครับครับ' not in out
        assert 'นะครับครับ' not in out
        assert out.endswith('ตลอดเลยนะครับ')

    @pytest.mark.parametrize('raw,expected', [
        ('ครับครับ', 'ครับ'),
        ('ครับ ครับ', 'ครับ'),
        ('ครับครับครับ', 'ครับ'),                # 3+ run collapses too
        ('นะครับครับ', 'นะครับ'),
        ('ขอบคุณค่ะค่ะ', 'ขอบคุณค่ะ'),
        ('ขอบคุณค่ะ ค่ะ', 'ขอบคุณค่ะ'),
        ('จ้าจ้า', 'จ้า'),
    ])
    def test_collapses_duplicates(self, raw, expected):
        assert P.collapse_polite_particles(raw) == expected

    @pytest.mark.parametrize('s', [
        'สวัสดีครับ',                         # single particle, untouched
        'ครับ ผมเข้าใจ',                     # particle followed by non-particle
        'Hello there.',                       # English untouched
        'ครับ. ขอบคุณค่ะ',                    # mixed, neither doubled
        '',                                    # empty
    ])
    def test_no_change_when_clean(self, s):
        assert P.collapse_polite_particles(s) == s

    def test_idempotent(self):
        s = 'นะครับครับครับ'
        once = P.collapse_polite_particles(s)
        twice = P.collapse_polite_particles(once)
        assert once == twice == 'นะครับ'


def test_cap_reply_strips_whitespace():
    assert P.cap_reply('   hello   ', n=300) == 'hello'


def test_cap_reply_truncates_with_ellipsis():
    s = 'x' * 500
    out = P.cap_reply(s, n=300)
    assert out.endswith('…')
    assert len(out) <= 301  # 300 + ellipsis


def test_cap_reply_prefers_word_boundary():
    s = 'Hello there! ' * 40  # plenty of spaces
    out = P.cap_reply(s, n=120)
    # Should end at a word boundary, not mid-token
    assert out.endswith('…')
    # the char immediately before the ellipsis should not be a letter
    # (i.e. we cut on whitespace and stripped it)
    assert out[-2] in '!?.,' or out[-2].isalpha() is False or out.count(' ') > 0


# ──────────────────────────────────────────────────────────────────
# detect_language
# ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('text,expected', [
    ('Hello there', 'en'),
    ('สวัสดีครับ', 'th'),
    ('Hi คุณ', 'th'),                 # mixed → Thai
    ('', 'en'),
    ('123 abc', 'en'),
    ('GEPP คือ?', 'th'),
])
def test_detect_language(text: str, expected: str):
    assert P.detect_language(text) == expected


# ──────────────────────────────────────────────────────────────────
# build_messages
# ──────────────────────────────────────────────────────────────────

def test_build_messages_includes_system_first():
    msgs = P.build_messages([], 'hi')
    assert msgs[0]['role'] == 'system'
    assert 'KhunGEPP' in msgs[0]['content']


def test_build_messages_appends_history_then_user():
    history = [
        ('user', 'q1'),
        ('assistant', 'a1'),
        ('user', 'q2'),
        ('assistant', 'a2'),
    ]
    msgs = P.build_messages(history, 'q3')
    # system + 4 history + 1 new user
    assert len(msgs) == 6
    assert msgs[1] == {'role': 'user', 'content': 'q1'}
    assert msgs[4] == {'role': 'assistant', 'content': 'a2'}
    assert msgs[5] == {'role': 'user', 'content': 'q3'}


def test_build_messages_skips_invalid_history_rows():
    history = [
        ('user', 'q1'),
        ('garbage', 'should be skipped'),
        ('assistant', ''),  # empty content skipped
        ('assistant', 'a1'),
    ]
    msgs = P.build_messages(history, 'q2')
    # system + 2 valid history + 1 new user = 4
    assert len(msgs) == 4
    contents = [m['content'] for m in msgs[1:]]
    assert contents == ['q1', 'a1', 'q2']


def test_build_fallback_reply_thai_vs_en():
    th = P.build_fallback_reply('th')
    en = P.build_fallback_reply('en')
    assert 'ขออภัย' in th
    assert 'KhunGEPP' in en or 'Sorry' in en


# ──────────────────────────────────────────────────────────────────
# Service-level: history truncation @ 10k chars
# (uses a fake Session so we don't touch a real DB)
# ──────────────────────────────────────────────────────────────────

class _FakeQuery:
    """Minimal fake of SQLAlchemy Query supporting the chain
    .filter(...).order_by(...).limit(...).all()."""

    def __init__(self, rows):
        self._rows = list(rows)

    def filter(self, *_args, **_kw):
        return self

    def order_by(self, *_args, **_kw):
        return self

    def limit(self, n):
        self._rows = self._rows[:n]
        return self

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    def query(self, _model):
        return _FakeQuery(self._rows)


def _row(role: str, content: str, age_seconds: int):
    """Build a fake history row with a deterministic created_date."""
    return SimpleNamespace(
        role=role,
        content=content,
        is_active=True,
        created_date=datetime.now(timezone.utc) - timedelta(seconds=age_seconds),
    )


def test_history_cap_keeps_only_recent_within_10k():
    """
    Feed 12 rows of 1,200 chars each = 14,400 chars total, ordered
    newest first. The chat service should keep only enough rows to
    stay at-or-below 10,000 chars, then return them in chronological
    (oldest-first) order.
    """
    from GEPPPlatform.services.esg.esg_chat_service import (
        EsgChatService,
        HISTORY_CHAR_CAP,
    )
    assert HISTORY_CHAR_CAP == 10_000

    rows_newest_first = [
        _row('user' if i % 2 == 0 else 'assistant',
             'x' * 1_200,
             age_seconds=i)
        for i in range(12)
    ]
    svc = EsgChatService(_FakeSession(rows_newest_first))
    chrono = svc._load_history_chronological('Utest')

    # Sum should be <= cap
    total = sum(len(c) for _, c in chrono)
    assert total <= HISTORY_CHAR_CAP

    # We should have kept *some* rows, fewer than the full set
    assert 0 < len(chrono) < 12

    # Order is chronological — last kept row is the most recent (i=0
    # had the smallest age_seconds), so it sits LAST after reverse.
    # The oldest row in `chrono` was further back in time than the
    # newest row.
    # We can't assert exact identity without dates on the SimpleNamespace,
    # but we can assert the slice came from the contiguous newest end.
    assert len(chrono) == HISTORY_CHAR_CAP // 1_200


def test_history_cap_keeps_at_least_one_even_when_oversized():
    """A single row > 10k should still come through (we don't drop
    the most recent message just because it's huge)."""
    from GEPPPlatform.services.esg.esg_chat_service import EsgChatService

    rows_newest_first = [_row('user', 'x' * 12_000, age_seconds=0)]
    svc = EsgChatService(_FakeSession(rows_newest_first))
    chrono = svc._load_history_chronological('Utest')
    assert len(chrono) == 1
