import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from hermes_tutor import daily_session, wire
from hermes_tutor.sessions import WARSAW
from hermes_tutor.store import Store


def event(text='convoluted', **source_overrides):
    source = dict(platform=SimpleNamespace(value='telegram'), chat_type='dm',
                  user_id='42', chat_id='42', is_bot=False)
    source.update(source_overrides)
    return SimpleNamespace(source=SimpleNamespace(**source), text=text, internal=False)


class DailySessionTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, TUTOR_OWNER_ID='42')
        self.env.start()
        self.addCleanup(self.env.stop)
        self.clock = patch('hermes_tutor.sessions.datetime')
        self.now = self.clock.start()
        self.addCleanup(self.clock.stop)
        self.now.now.return_value = datetime(2026, 10, 18, 9, tzinfo=WARSAW)
        self.entry = SimpleNamespace(created_at=datetime(2026, 10, 17, 19, tzinfo=WARSAW))
        self.store = SimpleNamespace(get_or_create_session=Mock(return_value=self.entry),
                                     reset_session=Mock(return_value=SimpleNamespace()))
        self.gateway = SimpleNamespace(_session_key_for_source=Mock(return_value='tutor-owner'),
                                       _is_session_running=Mock(return_value=False),
                                       _clear_conversation_scope=Mock(), _evict_cached_agent=Mock())

    def dispatch(self, incoming=None):
        return daily_session(incoming or event(), self.gateway, self.store)

    def test_new_day_resets_once_and_keeps_first_message(self):
        incoming = event()
        self.store.reset_session.side_effect = lambda key: setattr(
            self.entry, 'created_at', self.now.now.return_value) or self.entry
        self.assertIsNone(self.dispatch(incoming))
        self.assertIsNone(self.dispatch(incoming))
        self.store.reset_session.assert_called_once_with('tutor-owner')
        self.gateway._clear_conversation_scope.assert_called_once_with(
            'tutor-owner', reason='tutor_daily_reset')
        self.gateway._evict_cached_agent.assert_called_once_with('tutor-owner')
        self.assertEqual(incoming.text, 'convoluted')
        self.store.get_or_create_session.assert_called_with(incoming.source, touch_activity=False)

    def test_same_day_and_manual_new_session_are_preserved(self):
        self.entry.created_at = datetime(2026, 10, 18, 0, 1, tzinfo=WARSAW)
        self.dispatch()
        self.store.reset_session.assert_not_called()
        self.gateway._evict_cached_agent.assert_not_called()

    def test_date_boundary_uses_warsaw_instead_of_utc(self):
        self.entry.created_at = datetime(2026, 10, 17, 21, 59, tzinfo=timezone.utc)
        self.now.now.return_value = datetime(2026, 10, 18, 0, 1, tzinfo=WARSAW)
        self.dispatch()
        self.store.reset_session.assert_called_once()

    def test_spring_and_autumn_clock_changes_do_not_add_resets(self):
        for month, day in ((3, 29), (10, 25)):
            with self.subTest(month=month):
                self.entry.created_at = datetime(2026, month, day, 0, 1, tzinfo=WARSAW)
                self.now.now.return_value = datetime(2026, month, day, 23, 59, tzinfo=WARSAW)
                self.dispatch()
        self.store.reset_session.assert_not_called()

    def test_naive_hermes_timestamp_uses_server_local_timezone(self):
        aware = datetime(2026, 10, 18, 0, 1, tzinfo=WARSAW)
        self.entry.created_at = aware.astimezone().replace(tzinfo=None)
        self.dispatch()
        self.store.reset_session.assert_not_called()

    def test_missed_days_reset_on_next_message(self):
        self.entry.created_at = datetime(2026, 9, 1, tzinfo=WARSAW)
        self.dispatch()
        self.store.reset_session.assert_called_once()

    def test_busy_turn_is_not_interrupted_and_reset_waits_for_idle_message(self):
        self.gateway._is_session_running.return_value = True
        self.dispatch()
        self.store.get_or_create_session.assert_not_called()
        self.gateway._evict_cached_agent.assert_not_called()
        self.gateway._is_session_running.return_value = False
        self.dispatch()
        self.store.reset_session.assert_called_once()

    def test_commands_internal_events_and_other_senders_do_not_change_sessions(self):
        incoming = [event('/new'), event(' /reset'), event('/context'), event('/review'),
                    event(user_id='43'), event(chat_id='43'), event(chat_type='group'),
                    event(platform=SimpleNamespace(value='discord')), event(is_bot=True)]
        internal = event()
        internal.internal = True
        incoming.append(internal)
        for item in incoming:
            with self.subTest(item=item):
                self.assertIsNone(self.dispatch(item))
        with patch.dict(os.environ, TUTOR_OWNER_ID=''):
            self.dispatch()
        self.store.get_or_create_session.assert_not_called()
        self.store.reset_session.assert_not_called()

    def test_failed_reset_does_not_dispatch_yesterdays_context(self):
        self.store.reset_session.side_effect = RuntimeError('database unavailable')
        with self.assertLogs('hermes_tutor.sessions', level='ERROR'):
            result = self.dispatch()
        self.assertEqual(result, {'action': 'skip', 'reason': 'tutor_daily_session_reset_failed'})


class HermesSessionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        try:
            from gateway.config import GatewayConfig, Platform
            from gateway.session import SessionSource, SessionStore
            import telegram  # noqa: F401
        except ImportError:
            self.skipTest('Run with the tutor Hermes venv for native session checks')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, HERMES_HOME=self.tmp.name, TUTOR_OWNER_ID='42')
        self.env.start()
        self.addCleanup(self.env.stop)
        self.sessions = SessionStore(Path(self.tmp.name) / 'sessions', GatewayConfig())
        self.addCleanup(self.sessions._db.close)
        self.source = SessionSource(platform=Platform.TELEGRAM, user_id='42', chat_id='42')
        with patch('gateway.session._now', return_value=datetime(2026, 10, 17, 12)):
            self.old = self.sessions.get_or_create_session(self.source)
        self.sessions.append_to_transcript(self.old.session_id,
                                           {'role': 'user', 'content': 'yesterday'})
        self.gateway = SimpleNamespace(
            _session_key_for_source=self.sessions._generate_session_key,
            _is_session_running=lambda key: False,
            _clear_conversation_scope=Mock(), _evict_cached_agent=Mock())
        self.incoming = SimpleNamespace(source=self.source, text='convoluted', internal=False)

    async def test_real_store_keeps_old_transcript_and_starts_empty_once(self):
        with patch('hermes_tutor.sessions.datetime') as clock:
            clock.now.return_value = datetime(2026, 10, 18, 9, tzinfo=WARSAW)
            self.assertIsNone(daily_session(self.incoming, self.gateway, self.sessions))
            fresh = self.sessions.get_or_create_session(self.source, touch_activity=False)
            self.assertNotEqual(fresh.session_id, self.old.session_id)
            self.assertTrue(fresh.is_fresh_reset)
            self.assertEqual(self.sessions.load_transcript(fresh.session_id), [])
            self.assertEqual(self.sessions.load_transcript(self.old.session_id)[0]['content'], 'yesterday')
            self.assertIsNone(daily_session(self.incoming, self.gateway, self.sessions))
            self.assertEqual(self.sessions.get_or_create_session(self.source).session_id, fresh.session_id)

    async def test_review_button_and_card_survive_daily_reset(self):
        from unittest.mock import AsyncMock
        vocab = Store()
        vocab.save('test', 'word', '/test/', [dict(definition='an examination',
                   translation='тест', example='I passed the test.')], now=0)
        card = vocab.reserve('42')[0]
        vocab.delivered(card['token'], 10)
        self.assertIsNotNone(vocab.answer(card['token'], '42', 10, 'show'))
        handlers = []
        wire(SimpleNamespace(add_handler=handlers.append), None)
        query = SimpleNamespace(data=f'tutor:{card["token"]}:good',
                                message=SimpleNamespace(message_id=10),
                                answer=AsyncMock(), edit_message_text=AsyncMock())
        update = SimpleNamespace(effective_user=SimpleNamespace(id=42),
                                 effective_chat=SimpleNamespace(id=42, type='private'), callback_query=query)
        before = vocab.lookup('test')
        with patch('hermes_tutor.sessions.datetime') as clock:
            clock.now.return_value = datetime(2026, 10, 18, 9, tzinfo=WARSAW)
            self.assertIsNone(daily_session(self.incoming, self.gateway, self.sessions))
        self.assertEqual(vocab.lookup('test'), before)
        with patch('hermes_tutor.Store', return_value=vocab):
            await handlers[-1].callback(update, None)
            await handlers[-1].callback(update, None)
        self.assertEqual(vocab.lookup('test')['review_count'], 1)
        query.edit_message_text.assert_awaited_once()

    async def test_native_gateway_discards_cached_summary_and_conversation_state(self):
        from gateway.run import GatewayRunner
        gateway = object.__new__(GatewayRunner)
        gateway.session_store = self.sessions
        key = gateway._session_key_for_source(self.source)
        old_agent = SimpleNamespace(context_compressor=SimpleNamespace(_previous_summary='yesterday'))
        gateway._agent_cache = {key: (old_agent, 'signature')}
        gateway._pending_model_notes = {key: 'old override'}
        gateway._spawn_release_thread = Mock()
        state = gateway._session_state(key)
        state.conversation.ephemeral_pin = 'old prompt'
        state.persistent.approvals = 'old approvals'
        with patch('hermes_tutor.sessions.datetime') as clock:
            clock.now.return_value = datetime(2026, 10, 18, 9, tzinfo=WARSAW)
            self.assertIsNone(daily_session(self.incoming, gateway, self.sessions))
        self.assertNotIn(key, gateway._agent_cache)
        self.assertNotIn(key, gateway._pending_model_notes)
        self.assertIsNone(state.conversation.ephemeral_pin)
        self.assertIsNone(state.persistent.approvals)
        gateway._spawn_release_thread.assert_called_once()


if __name__ == '__main__':
    unittest.main()
