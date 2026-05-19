"""
EsgChatService — KhunGEPP conversation orchestration.

Single entry point: `EsgChatService(db).reply_to_text(...)`.

What it does:
  1. Sanity-check the inbound text and detect language.
  2. Pull the most recent chat-history rows for the LINE user, walk
     newest → oldest until the running content total exceeds
     HISTORY_CHAR_CAP (10k chars), reverse to chronological order.
  3. Compose the OpenAI-style messages (system + history + new user).
  4. Call OpenRouter via prompts.esg_chat.clients.llm_client. On any
     exception, swap the reply for a localised fallback so the user
     never sees a raw error.
  5. Cap the reply at DEFAULT_REPLY_CHAR_CAP (300 chars) and persist
     both the user message and the assistant reply as
     `EsgLineChatHistory` rows in a single transaction.

The conversation key is always `line_user_id`. `organization_id` is
optional — unregistered leads have NULL, registered users have the
org they currently belong to. We do NOT backfill old NULL rows when
a lead later joins; that's intentional so admins can see when the
relationship started.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from ...models.esg.line_chat_histories import EsgLineChatHistory
from ...prompts.esg_chat import prompts as chat_prompts
from ...prompts.esg_chat.clients.llm_client import chat_complete

logger = logging.getLogger(__name__)


# Hard limits. The 10k char cap matches the user spec; the 300 char
# reply cap matches the requested 200-300 conversational tone.
HISTORY_CHAR_CAP = chat_prompts.HISTORY_CHAR_CAP
REPLY_CHAR_CAP = chat_prompts.DEFAULT_REPLY_CHAR_CAP

# Defensive upper bound on inbound user text. LINE allows up to 5000
# chars per message but we don't need anywhere near that for KhunGEPP
# — anything past this is almost certainly a paste, and the model
# reply budget can't usefully respond to it anyway.
USER_TEXT_MAX = 4_000

# How many recent rows to consider before applying the char-cap walk.
# 200 turns × 100 chars avg ≈ 20k chars worst case, well above the
# 10k window we'll keep, and a hard SQL `LIMIT` keeps queries fast.
HISTORY_FETCH_LIMIT = 200


class EsgChatService:
    """KhunGEPP chat orchestrator. Holds a SQLAlchemy session."""

    def __init__(self, db: Session):
        self.db = db

    # ── public ─────────────────────────────────────────────────────

    def reply_to_text(
        self,
        line_user_id: str,
        organization_id: Optional[int],
        text: str,
    ) -> str:
        """
        Generate a KhunGEPP reply for `text` from LINE user
        `line_user_id`. Persists user + assistant rows. Always
        returns a non-empty string suitable to send back via
        `_send_text_reply` — never raises on LLM/persistence errors.
        """
        if not line_user_id:
            raise ValueError('line_user_id is required')
        text = (text or '').strip()
        if not text:
            # An empty inbound is silently dropped — LINE never sends
            # one in practice, but if a sticker/emoji-only message
            # somehow lands here, return a friendly nudge.
            return 'สวัสดีครับ มีอะไรให้คุณเก็บช่วยไหมครับ?'
        if len(text) > USER_TEXT_MAX:
            text = text[:USER_TEXT_MAX]

        language = chat_prompts.detect_language(text)

        # 1) load history (newest first), then truncate by char budget
        history_chrono = self._load_history_chronological(line_user_id)

        # 2) compose messages
        messages = chat_prompts.build_messages(history_chrono, text)

        # Visibility — confirms in CloudWatch that the model is being
        # given the prior conversation. If history rows == 0 on a
        # follow-up question we know the retrieval failed (wrong key,
        # rows soft-deleted, etc.). Char counts let us verify the 10k
        # cap walk is doing its job.
        history_chars = sum(len(c or '') for _, c in history_chrono)
        logger.info(
            '[CHAT] llm-call line_user=%s org=%s history_rows=%d '
            'history_chars=%d input_chars=%d',
            (line_user_id or '')[:12], organization_id,
            len(history_chrono), history_chars, len(text),
        )

        # 3) call LLM, with graceful fallback
        reply_text = ''
        model_used: Optional[str] = None
        tokens_in: Optional[int] = None
        tokens_out: Optional[int] = None
        try:
            resp = chat_complete(messages)
            reply_text = (resp.get('content') or '').strip()
            model_used = resp.get('model')
            usage = resp.get('usage') or {}
            tokens_in = usage.get('prompt_tokens')
            tokens_out = usage.get('completion_tokens')
        except Exception:
            logger.exception(
                '[CHAT] LLM call failed for line_user=%s',
                line_user_id[:12] if line_user_id else '?',
            )
            reply_text = ''  # falls through to fallback below

        if not reply_text:
            reply_text = chat_prompts.build_fallback_reply(language)

        # 4) collapse doubled Thai polite particles ("นะครับครับ" →
        #    "นะครับ") that the model produces despite the prompt
        #    rule, then cap the reply to the chat budget.
        cleaned = chat_prompts.collapse_polite_particles(reply_text)
        capped = chat_prompts.cap_reply(cleaned, REPLY_CHAR_CAP)

        # 5) persist BOTH rows in one transaction. If the persistence
        #    itself fails we still hand the reply back to the caller —
        #    we'd rather the user see KhunGEPP's response than nothing.
        try:
            self._persist_turn(
                line_user_id=line_user_id,
                organization_id=organization_id,
                user_text=text,
                assistant_text=capped,
                language=language,
                model=model_used,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
            )
        except Exception:
            logger.exception(
                '[CHAT] failed to persist chat history for line_user=%s',
                line_user_id[:12] if line_user_id else '?',
            )
            try:
                self.db.rollback()
            except Exception:
                pass

        return capped

    # ── helpers ────────────────────────────────────────────────────

    def _load_history_chronological(
        self, line_user_id: str,
    ) -> List[Tuple[str, str]]:
        """
        Pull the most recent active history rows, walk newest → oldest
        accumulating content length, stop once we'd exceed
        HISTORY_CHAR_CAP, then reverse the kept slice into
        chronological order so the model sees the conversation in
        natural sequence.
        """
        rows = (
            self.db.query(EsgLineChatHistory)
            .filter(
                EsgLineChatHistory.line_user_id == line_user_id,
                EsgLineChatHistory.is_active.is_(True),
            )
            .order_by(EsgLineChatHistory.created_date.desc())
            .limit(HISTORY_FETCH_LIMIT)
            .all()
        )
        kept: List[Tuple[str, str]] = []
        running = 0
        for row in rows:
            content = row.content or ''
            length = len(content)
            if running + length > HISTORY_CHAR_CAP and kept:
                break
            kept.append((row.role, content))
            running += length
        kept.reverse()  # newest-first → chronological
        return kept

    def _persist_turn(
        self,
        line_user_id: str,
        organization_id: Optional[int],
        user_text: str,
        assistant_text: str,
        language: str,
        model: Optional[str],
        tokens_in: Optional[int],
        tokens_out: Optional[int],
    ) -> None:
        user_row = EsgLineChatHistory(
            line_user_id=line_user_id,
            organization_id=organization_id,
            role='user',
            content=user_text,
            language=language,
        )
        assistant_row = EsgLineChatHistory(
            line_user_id=line_user_id,
            organization_id=organization_id,
            role='assistant',
            content=assistant_text,
            language=language,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
        self.db.add(user_row)
        self.db.add(assistant_row)
        self.db.commit()
        logger.info(
            '[CHAT] persisted turn line_user=%s org=%s lang=%s '
            'in/out=%s/%s tokens=%s/%s',
            line_user_id[:12] if line_user_id else '?',
            organization_id,
            language,
            len(user_text), len(assistant_text),
            tokens_in, tokens_out,
        )
