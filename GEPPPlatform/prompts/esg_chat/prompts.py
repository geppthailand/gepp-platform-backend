"""
KhunGEPP — composed system prompt + helpers.

Three responsibilities:

1. Compose the immutable system prompt from the persona / tone /
   topic / refusal blocks plus the public GEPP facts.
2. Build an OpenAI-style `messages` list out of (system, history
   rows, new user message).
3. Cap an LLM reply at the configured character budget so a single
   chat turn never spams the LINE conversation.

Nothing here calls the LLM directly — see `clients.llm_client`.
"""

from __future__ import annotations

import re
from typing import Iterable

from .gepp_facts import GEPP_PUBLIC_FACTS
from .style_guide import (
    PERSONA,
    TONE_AND_STYLE,
    TOPIC_SCOPE,
    REFUSAL_RULES,
)


# Hard cap a single chat reply will be truncated to. Configured at the
# service boundary, but kept here too as a defence-in-depth guard.
DEFAULT_REPLY_CHAR_CAP = 300

# Conversation history character budget. The chat service walks
# history newest → oldest accumulating `len(content)` and stops once
# the running sum exceeds this. The 10k matches the user spec.
HISTORY_CHAR_CAP = 10_000


# ──────────────────────────────────────────────────────────────────
# System prompt — composed once at import.
# ──────────────────────────────────────────────────────────────────

KHUN_GEPP_SYSTEM_PROMPT = "\n\n".join([
    PERSONA.strip(),
    TONE_AND_STYLE.strip(),
    TOPIC_SCOPE.strip(),
    REFUSAL_RULES.strip(),
    GEPP_PUBLIC_FACTS.strip(),
])


# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────

def build_messages(
    history: Iterable[tuple[str, str]],
    user_text: str,
) -> list[dict]:
    """
    Compose the OpenAI/OpenRouter `messages` payload.

    `history` is an iterable of (role, content) tuples in
    chronological order — already truncated by the chat service to
    the most recent ~10k chars total. role ∈ {'user', 'assistant'}.

    The new user message is appended at the end so the model sees
    the conversation in the order the user lived it.
    """
    msgs: list[dict] = [
        {'role': 'system', 'content': KHUN_GEPP_SYSTEM_PROMPT},
    ]
    for role, content in history:
        if role not in ('user', 'assistant'):
            continue
        if not content:
            continue
        msgs.append({'role': role, 'content': content})
    msgs.append({'role': 'user', 'content': user_text})
    return msgs


def cap_reply(text: str, n: int = DEFAULT_REPLY_CHAR_CAP) -> str:
    """
    Hard-cap a chat reply at `n` characters. Prefer to slice on the
    last whitespace before `n` so we don't cut mid-word, and append
    `…` to signal truncation.

    `n` matches the user-stated budget of 200-300 chars; we default
    to 300 (the upper bound) but the caller can pass a tighter value.
    """
    if not text:
        return ''
    s = text.strip()
    if len(s) <= n:
        return s
    # Find a clean break point — last whitespace within the budget.
    # If the message has no whitespace (CJK / Thai), just hard-slice.
    head = s[:n]
    cut = max(head.rfind(' '), head.rfind('\n'))
    if cut > n - 60:
        # whitespace is "close enough" to the budget — use it
        head = head[:cut].rstrip()
    return head.rstrip() + '…'


# Adjacent polite-particle collapser. LLMs reliably double Thai
# polite particles ("ครับครับ", "นะครับครับ", "ค่ะค่ะ") even when
# the system prompt forbids it — small grammatical tic the model
# can't reliably suppress. This regex squashes any run of repeated
# polite particles down to one, with optional whitespace between
# the duplicates. Order in the alternation matters: longer
# particles must come before their substrings (e.g. 'ครับ' before
# the bare honorific).
_POLITE_PARTICLES = ('ครับ', 'ค่ะ', 'คะ', 'ครับผม', 'ค้าบ', 'จ้า', 'จ้ะ')
_POLITE_DUP_RE = re.compile(
    r'(' + '|'.join(sorted(_POLITE_PARTICLES, key=len, reverse=True)) + r')'
    r'(?:\s*\1)+'
)


def collapse_polite_particles(text: str) -> str:
    """
    Collapse adjacent doubled Thai polite particles down to one.

      "นะครับครับ"            → "นะครับ"
      "ครับ ครับ"             → "ครับ"
      "ขอบคุณค่ะ ค่ะ"           → "ขอบคุณค่ะ"
      "เข้าใจครับครับครับ"      → "เข้าใจครับ"

    Single particles, sentence-final ครับ/ค่ะ in the middle of a
    paragraph, and English text are left alone.
    """
    if not text:
        return ''
    return _POLITE_DUP_RE.sub(r'\1', text)


def detect_language(text: str) -> str:
    """
    Cheap language detection: any Thai char → 'th', else 'en'.
    'mixed' is left for a future caller; we only care about
    "should we reply in Thai?" today, which the system prompt
    instructs the model to do whenever any Thai is present.
    """
    if not text:
        return 'en'
    for ch in text:
        # Thai Unicode block: U+0E00 – U+0E7F
        if '฀' <= ch <= '๿':
            return 'th'
    return 'en'


def build_fallback_reply(language: str) -> str:
    """Localised graceful fallback when the LLM call fails."""
    if language == 'th':
        return 'ขออภัยครับ ระบบขัดข้องชั่วคราว ลองใหม่อีกครั้งนะครับ'
    return "Sorry — KhunGEPP is having a hiccup. Please try again in a moment."
