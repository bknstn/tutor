import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from hermes_tutor import send_reviews, wire
from hermes_tutor.store import INTERVALS, Store


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / 'cards.db')
        self.now = 90000

    def words(self, count):
        for number in range(count):
            self.store.save(f'term {number}', 'word', '/tɜːm/',
                            [dict(definition='a word', translation='слово', example='A useful term.')], now=0)

    def start(self, scheduled=True):
        batch = self.store.start_review('42', scheduled=scheduled, now=self.now)
        self.store.deliver_review(batch['token'], 10)
        return batch

    def action(self, batch, action):
        return self.store.review_action(batch['token'], batch['revision'], '42', 10, action, now=self.now)

    def finish(self, batch):
        while batch['state'] == 'active':
            batch = self.action(batch, 'show')
            batch = self.action(batch, 'good')
        return batch

    def test_100_words_offer_only_ten_then_wait_for_consent(self):
        self.words(100)
        batch = self.start()
        self.assertEqual(batch['total'], 10)
        premature = self.action(batch, 'more')
        self.assertEqual(premature['token'], batch['token'])
        completed = self.finish(batch)
        self.assertEqual(completed['done'], 10)
        self.assertEqual(completed['state'], 'complete')
        self.assertIsNone(self.store.start_review('42', scheduled=True, now=self.now))
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM review_items').fetchone()[0], 10)
            self.assertEqual(db.execute('SELECT SUM(review_count) FROM cards').fetchone()[0], 10)
        child = self.action(completed, 'more')
        self.assertEqual(child['total'], 10)
        self.assertNotEqual(child['token'], completed['token'])
        self.assertEqual(child['message_id'], 10)
        repeated = self.action(completed, 'more')
        self.assertEqual(repeated['token'], child['token'])
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM review_items').fetchone()[0], 20)

    def test_replayed_rating_cannot_rate_the_next_card(self):
        self.words(2)
        shown = self.action(self.start(), 'show')
        next_card = self.action(shown, 'easy')
        replayed = self.action(shown, 'again')
        self.assertEqual(replayed, next_card)
        self.assertEqual(self.store.lookup('term 0')['review_count'], 1)
        self.assertEqual(self.store.lookup('term 1')['review_count'], 0)
        unrevealed = self.action(next_card, 'good')
        self.assertEqual(unrevealed, next_card)

    def test_stop_releases_unanswered_cards_without_changing_their_schedule(self):
        self.words(15)
        batch = self.start()
        batch = self.action(self.action(batch, 'show'), 'good')
        before = self.store.lookup('term 1')
        stopped = self.action(batch, 'stop')
        self.assertEqual(stopped['state'], 'stopped')
        self.assertEqual(stopped['done'], 1)
        self.assertIsNone(self.store.start_review('42', scheduled=True, now=self.now))
        self.assertEqual(self.store.lookup('term 1'), before)
        requested = self.store.start_review('42', now=self.now)
        self.assertEqual(requested['total'], 10)
        self.assertEqual(requested['card']['term'], 'term 1')
        self.assertEqual(self.action(stopped, 'more')['state'], 'stopped')

    def test_parallel_scheduled_runs_and_consent_clicks_are_single_flight(self):
        self.words(100)
        with ThreadPoolExecutor(max_workers=4) as pool:
            runs = list(pool.map(lambda _: self.store.start_review('42', scheduled=True, now=self.now), range(4)))
        batches = [batch for batch in runs if batch]
        self.assertEqual(len(batches), 1)
        self.store.deliver_review(batches[0]['token'], 10)
        complete = self.finish(batches[0])
        with ThreadPoolExecutor(max_workers=4) as pool:
            continuations = list(pool.map(lambda _: self.action(complete, 'more'), range(4)))
        self.assertEqual(len({batch['token'] for batch in continuations}), 1)
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM review_batches').fetchone()[0], 2)

    def test_progress_survives_restart_and_manual_request_resumes_it(self):
        self.words(12)
        shown = self.action(self.start(), 'show')
        self.store = Store(self.store.path)
        resumed = self.store.start_review('42', now=self.now)
        self.assertFalse(resumed['created'])
        self.assertEqual(resumed['token'], shown['token'])
        self.assertTrue(resumed['card']['revealed'])
        self.assertEqual(self.action(resumed, 'good')['done'], 1)

    def test_wrong_user_message_and_expired_buttons_do_not_grade(self):
        self.words(12)
        batch = self.start()
        for chat, message, now in (('43', 10, self.now), ('42', 11, self.now),
                                   ('42', 10, self.now + 20 * 3600)):
            self.assertIsNone(self.store.review_action(batch['token'], 0, chat, message, 'show', now=now))
        self.now += 86400
        fresh = self.start()
        self.assertNotEqual(fresh['token'], batch['token'])
        self.assertEqual(fresh['card']['term'], 'term 0')
        self.assertIsNone(self.action(batch, 'stop'))

    def test_schedule_is_deduplicated_by_warsaw_date_not_utc_date(self):
        self.words(12)
        self.now = int(datetime(2026, 10, 17, 22, 30, tzinfo=timezone.utc).timestamp())
        batch = self.start()
        self.action(batch, 'stop')
        self.now += 2 * 3600
        self.assertIsNone(self.store.start_review('42', scheduled=True, now=self.now))
        self.now += 24 * 3600
        self.assertIsNotNone(self.store.start_review('42', scheduled=True, now=self.now))

    def test_failed_unbound_delivery_can_retry_but_orphan_buttons_cannot_grade(self):
        self.words(12)
        failed = self.store.start_review('42', scheduled=True, now=self.now)
        self.store.abandon_review(failed['token'])
        retry = self.start()
        self.assertEqual(retry['total'], 10)
        self.assertNotEqual(retry['token'], failed['token'])
        self.assertIsNone(self.action(failed, 'show'))

    def test_all_intervals_and_partial_final_batch(self):
        self.words(3)
        batch = self.start()
        for index, (action, days) in enumerate(INTERVALS.items()):
            batch = self.action(self.action(batch, 'show'), action)
            card = self.store.lookup(f'term {index}')
            self.assertEqual(card['next_review_at'], self.now + days * 86400)
            self.assertEqual(card['review_count'], 1)
        self.assertEqual(batch['state'], 'complete')
        self.assertEqual(batch['more'], 0)

    def test_old_consent_cannot_open_a_second_active_panel(self):
        self.words(30)
        old = self.finish(self.start(scheduled=False))
        scheduled = self.store.start_review('42', scheduled=True, now=self.now)
        self.store.deliver_review(scheduled['token'], 11)
        self.assertIsNone(self.action(old, 'more'))
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM review_batches WHERE state='active'").fetchone()[0], 1)


class ReviewPanelTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        try:
            import telegram  # noqa: F401
        except ImportError:
            self.skipTest('Run with the tutor Hermes venv for Telegram integration checks')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / 'cards.db')
        for index in range(100):
            self.store.save(f'term {index}', 'word', '/tɜːm/',
                            [dict(definition='a word', translation='слово', example='A useful term.')], now=0)
        self.bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=10)),
                                   edit_message_text=AsyncMock())
        self.handlers = []
        wire(SimpleNamespace(add_handler=self.handlers.append), None)
        self.handler = next(handler.callback for handler in self.handlers
                            if getattr(getattr(handler, 'pattern', None), 'pattern', '').startswith('^tutorq:'))
        self.query = SimpleNamespace(data='', message=SimpleNamespace(message_id=10),
                                     answer=AsyncMock(), edit_message_text=AsyncMock())
        self.update = SimpleNamespace(effective_user=SimpleNamespace(id=42),
                                       effective_chat=SimpleNamespace(id=42, type='private'), callback_query=self.query)
        self.env = patch.dict(os.environ, TUTOR_OWNER_ID='42')
        self.env.start()
        self.addCleanup(self.env.stop)
        self.storage = patch('hermes_tutor.Store', return_value=self.store)
        self.storage.start()
        self.addCleanup(self.storage.stop)

    def callback(self, content, action):
        return next(button.callback_data for row in content['reply_markup'].inline_keyboard
                    for button in row if button.callback_data.endswith(':' + action))

    async def press(self, content, action):
        self.query.data = self.callback(content, action)
        await self.handler(self.update, None)
        return self.query.edit_message_text.call_args.kwargs

    async def test_100_due_words_use_one_message_with_explicit_continuation(self):
        self.assertEqual(await send_reviews(self.bot, '42', self.store, scheduled=True), 10)
        self.assertEqual(await send_reviews(self.bot, '42', self.store, scheduled=True), 0)
        content = self.bot.send_message.call_args.kwargs
        for index in range(10):
            self.assertIn(f'{index + 1}/10', content['text'])
            content = await self.press(content, 'show')
            self.assertIn('Meaning: a word', content['text'])
            content = await self.press(content, 'good')
        self.assertIn('Продолжить?', content['text'])
        self.bot.send_message.assert_awaited_once()
        content = await self.press(content, 'more')
        self.assertIn('1/10', content['text'])
        self.assertIn('term 10', content['text'])
        content = await self.press(content, 'stop')
        self.assertIsNone(content['reply_markup'])
        self.bot.send_message.assert_awaited_once()

    async def test_failed_edit_is_recoverable_without_double_grading(self):
        await send_reviews(self.bot, '42', self.store)
        shown = await self.press(self.bot.send_message.call_args.kwargs, 'show')
        self.query.data = self.callback(shown, 'good')
        self.query.edit_message_text.side_effect = [RuntimeError('network timeout'), None]
        with self.assertLogs('hermes_tutor', level='ERROR'):
            await self.handler(self.update, None)
        await self.handler(self.update, None)
        self.assertEqual(self.store.lookup('term 0')['review_count'], 1)
        self.assertEqual(self.store.lookup('term 1')['review_count'], 0)
        self.assertIn('2/10', self.query.edit_message_text.call_args.kwargs['text'])

    async def test_manual_review_restores_panel_without_another_message(self):
        await send_reviews(self.bot, '42', self.store)
        self.assertIsNone(await send_reviews(self.bot, '42', self.store))
        self.bot.send_message.assert_awaited_once()
        self.bot.edit_message_text.assert_awaited_once()
        self.assertEqual(self.bot.edit_message_text.call_args.kwargs['message_id'], 10)

    async def test_unauthorized_and_unbound_buttons_never_edit_a_panel(self):
        await send_reviews(self.bot, '42', self.store)
        self.query.data = self.callback(self.bot.send_message.call_args.kwargs, 'show')
        self.update.effective_user.id = 43
        await self.handler(self.update, None)
        self.update.effective_user.id = 42
        self.query.message.message_id = 11
        await self.handler(self.update, None)
        self.query.edit_message_text.assert_not_awaited()

    async def test_storage_failure_is_reported_without_changing_the_panel(self):
        await send_reviews(self.bot, '42', self.store)
        self.query.data = self.callback(self.bot.send_message.call_args.kwargs, 'show')
        with patch.object(self.store, 'review_action', side_effect=RuntimeError('storage unavailable')):
            with self.assertLogs('hermes_tutor', level='ERROR'):
                await self.handler(self.update, None)
        self.query.edit_message_text.assert_not_awaited()
        self.assertTrue(self.query.answer.call_args.kwargs['show_alert'])

    async def test_empty_scheduled_review_sends_nothing(self):
        empty = Store(Path(self.tmp.name) / 'empty.db')
        self.assertEqual(await send_reviews(self.bot, '42', empty, scheduled=True), 0)
        self.bot.send_message.assert_not_awaited()

    async def test_rendering_fits_telegram_limits_and_callback_budget(self):
        from hermes_tutor.reviews import review_content
        meanings = [dict(definition=chr(97 + index) * 300, translation='я' * 300, example='x' * 300)
                    for index in range(3)]
        self.store.save('a' * 160, 'word', 'x' * 160, meanings, now=0)
        batch = self.store.start_review('42')
        batch['card'] = self.store.lookup('a' * 160)
        batch['card']['revealed'] = True
        for state in ('active', 'complete', 'stopped'):
            batch['state'] = state
            batch['more'] = 10
            content = review_content(batch)
            self.assertLessEqual(len(content['text']), 4096)
            for row in content['reply_markup'].inline_keyboard if content['reply_markup'] else []:
                for button in row:
                    self.assertLessEqual(len(button.callback_data.encode()), 64)


if __name__ == '__main__':
    unittest.main()
