"""Start an owner's vocabulary conversation afresh each Warsaw calendar day."""
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)
WARSAW = ZoneInfo('Europe/Warsaw')


def daily_session(event, gateway, session_store, **kwargs):
    """Native pre_gateway_dispatch hook; review buttons never enter this path."""
    source = event.source
    owner = os.environ.get('TUTOR_OWNER_ID', '')
    platform = getattr(source.platform, 'value', source.platform)
    if (not owner or platform != 'telegram' or source.chat_type != 'dm'
            or str(source.user_id) != owner or str(source.chat_id) != owner
            or getattr(source, 'is_bot', False) or getattr(event, 'internal', False)
            or (event.text or '').lstrip().startswith('/')):
        return

    try:
        session_key = gateway._session_key_for_source(source)
        # Finish a turn already in progress, including follow-ups queued around midnight.
        # The next idle user message starts the new day; never interrupt an active save.
        if gateway._is_session_running(session_key):
            return
        entry = session_store.get_or_create_session(source, touch_activity=False)
        # Hermes stores naive server-local timestamps. astimezone interprets those in
        # the server timezone, while also accepting aware timestamps from the store.
        if entry.created_at.astimezone(WARSAW).date() >= datetime.now(WARSAW).date():
            return
        # Discard cached summaries before publishing the new routing entry. If
        # storage fails, a retry cannot accidentally reuse yesterday's agent.
        gateway._clear_conversation_scope(session_key, reason='tutor_daily_reset')
        gateway._evict_cached_agent(session_key)
        new_entry = session_store.reset_session(session_key)
        if new_entry is None:
            raise RuntimeError('Session disappeared during daily reset')
        log.info('Started a fresh Tutor session for the Warsaw calendar day')
    except Exception:
        # Hook exceptions normally fail open in Hermes. Do not send yesterday's
        # conversation to the model when the requested fresh start failed.
        log.exception('Daily Tutor session reset failed; incoming message was not processed')
        return {'action': 'skip', 'reason': 'tutor_daily_session_reset_failed'}
