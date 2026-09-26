import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from hermes_tutor import authorized, send_reviews, wire
from hermes_tutor.store import Store


class TelegramTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        try:
            import telegram  # noqa: F401
        except ImportError:
            self.skipTest('Run with the Hermes venv for Telegram integration checks')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / 'cards.db')
        self.store.save('rule out', 'phrasal_verb', 'exclude', 'исключать', 'We can rule it out.', now=0)

    async def test_delivery_failure_retries_and_success_is_not_resent(self):
        bot = SimpleNamespace(send_message=AsyncMock(side_effect=RuntimeError('network down')))
        with self.assertRaises(RuntimeError):
            await send_reviews(bot, '42', self.store)
        bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=10))
        self.assertEqual(await send_reviews(bot, '42', self.store), 1)
        self.assertEqual(await send_reviews(bot, '42', self.store), 0)
        self.assertIn('tutor:', bot.send_message.call_args.kwargs['reply_markup'].inline_keyboard[0][0].callback_data)

    async def test_native_callback_updates_once(self):
        handlers = []
        wire(SimpleNamespace(add_handler=handlers.append), None)
        bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=10)))
        await send_reviews(bot, '42', self.store)
        data = bot.send_message.call_args.kwargs['reply_markup'].inline_keyboard[0][0].callback_data
        query = SimpleNamespace(data=data, message=SimpleNamespace(message_id=10),
                                answer=AsyncMock(), edit_message_text=AsyncMock())
        update = SimpleNamespace(effective_user=SimpleNamespace(id=42),
                                 effective_chat=SimpleNamespace(id=42, type='private'), callback_query=query)
        with patch.dict(os.environ, TUTOR_OWNER_ID='42'), patch('hermes_tutor.Store', return_value=self.store):
            await handlers[-1].callback(update, None)
            query.data = data.replace(':show', ':good')
            await handlers[-1].callback(update, None)
            await handlers[-1].callback(update, None)
        self.assertEqual(self.store.lookup('rule out')['review_count'], 1)
        self.assertEqual(query.edit_message_text.await_count, 2)


class AccessTests(unittest.TestCase):
    def test_owner_only_private_chat(self):
        with patch.dict(os.environ, TUTOR_OWNER_ID='42'):
            for user, chat, kind, expected in [(42, 42, 'private', True), (43, 42, 'private', False),
                                               (42, -1, 'group', False), (42, 43, 'private', False)]:
                update = SimpleNamespace(effective_user=SimpleNamespace(id=user),
                                         effective_chat=SimpleNamespace(id=chat, type=kind))
                self.assertEqual(authorized(update), expected)


if __name__ == '__main__':
    unittest.main()
