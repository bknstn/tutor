import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from hermes_tutor import authorized, format_card, register, send_reviews, tool, wire
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
        self.meanings = [
            {'definition': 'exclude a possibility', 'translation': 'исключать возможность',
             'example': 'We cannot rule out rain.'},
            {'definition': 'prevent an option from being possible', 'translation': 'делать невозможным',
             'example': 'The cost rules out a new car.'}]
        self.store.save('rule out', 'phrasal_verb', '/ruːl aʊt/', self.meanings, now=0)

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
            revealed = query.edit_message_text.call_args.args[0]
            self.assertIn('IPA: /ruːl aʊt/', revealed)
            for index, meaning in enumerate(self.meanings, 1):
                self.assertIn(f'{index}. Meaning: {meaning["definition"]}', revealed)
                self.assertIn(f'RU: {meaning["translation"]}', revealed)
                self.assertIn(f'Example: {meaning["example"]}', revealed)
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


class CardTests(unittest.TestCase):
    def test_single_meaning_and_legacy_rendering(self):
        meaning = {'definition': 'a repayment', 'translation': 'возмещение',
                   'example': 'I requested reimbursement.'}
        card = {'term': 'reimbursement', 'pronunciation': '/ˌriːɪmˈbɜːsmənt/',
                'meanings': [meaning]}
        self.assertIn('IPA:', format_card(card))
        self.assertIn('Meaning: a repayment', format_card(card))
        self.assertNotIn('1. Meaning', format_card(card))
        card['pronunciation'] = ''
        self.assertNotIn('IPA:', format_card(card))

    def test_maximum_card_fits_telegram_message(self):
        meaning = {key: 'x' * 300 for key in ('definition', 'translation', 'example')}
        card = {'term': 'x' * 160, 'pronunciation': 'x' * 160, 'meanings': [meaning] * 3}
        self.assertLess(len(format_card(card)), 4096)

    def test_tool_saves_and_enforces_content_fields(self):
        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, HERMES_HOME=home):
            args = {'action': 'save', 'term': 'test', 'type': 'word', 'pronunciation': '/test/',
                    'meanings': [{'definition': 'an examination', 'translation': 'тест',
                                  'example': 'I passed the test.'}]}
            self.assertEqual(json.loads(tool(args))['status'], 'saved')
            card = json.loads(tool({'action': 'lookup', 'term': 'test'}))['card']
            self.assertEqual(card['meanings'], args['meanings'])
            self.assertEqual(card['pronunciation'], args['pronunciation'])
            self.assertEqual(json.loads(tool(args))['status'], 'already_saved')
            self.assertEqual(json.loads(tool({**args, 'action': 'enrich', 'type': 'word'})).keys(), {'error'})
            self.assertEqual(json.loads(tool({key: value for key, value in
                                              {**args, 'action': 'enrich'}.items() if key != 'type'}))['status'], 'unchanged')
            self.assertIn('error', json.loads(tool({**args, 'term': 'invalid', 'pronunciation': ''})))
            self.assertIsNone(json.loads(tool({'action': 'lookup', 'term': 'invalid'}))['card'])

    def test_schema_exposes_pronunciation_and_structured_meanings(self):
        ctx = SimpleNamespace(register_tool=lambda **kwargs: tools.append(kwargs),
                              register_platform_handler=lambda *args: None)
        tools = []
        register(ctx)
        properties = tools[0]['schema']['parameters']['properties']
        self.assertIn('pronunciation', properties)
        self.assertEqual(properties['meanings']['items']['required'],
                         ['definition', 'translation', 'example'])


if __name__ == '__main__':
    unittest.main()
