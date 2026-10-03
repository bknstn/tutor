import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from hermes_tutor.store import Store, INTERVALS


class VocabularyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / 'cards.db')

    def save(self, term='rule out'):
        return self.store.save(term, 'phrasal_verb', '/ruːl aʊt/', [
            {'definition': 'exclude a possibility', 'translation': 'исключать',
             'example': 'We cannot rule out rain.'}], now=1000)

    def test_pronunciation_and_multiple_meanings_persist_and_reveal(self):
        meanings = [
            {'definition': 'behave towards someone', 'translation': 'обращаться с кем-либо',
             'example': 'They treat her kindly.'},
            {'definition': 'give medical care', 'translation': 'лечить',
             'example': 'This medicine treats infections.'}]
        self.store.save('treat', 'word', '/triːt/', meanings, now=1000)
        reloaded = Store(self.store.path)
        self.assertEqual(reloaded.lookup('treat')['meanings'], meanings)
        card = reloaded.reserve('42', now=90000)[0]
        self.assertEqual(card['pronunciation'], '/triːt/')
        self.assertEqual(card['meanings'], meanings)
        reloaded.delivered(card['token'], 7)
        revealed = reloaded.answer(card['token'], '42', 7, 'show', now=90001)
        self.assertEqual(revealed['meanings'], meanings)
        self.assertEqual(revealed['pronunciation'], '/triːt/')

    def test_repeated_definition_keeps_one_stored_and_returned_meaning(self):
        primary = {'definition': 'Money paid back for expenses.',
                   'translation': 'возмещение расходов',
                   'example': 'You can claim reimbursement for travel.'}
        duplicate = {'definition': '  ＭＯＮＥＹ paid  back for expenses! ',
                     'translation': 'компенсация затрат',
                     'example': 'Reimbursement usually takes a week.'}
        result = self.store.save('reimbursement', 'word', '/ˌriːɪmˈbɜːsmənt/',
                                 [primary, duplicate], now=1000)
        self.assertEqual(result['status'], 'saved')
        self.assertEqual(result['card']['meanings'], [primary])
        self.assertEqual(Store(self.store.path).lookup('reimbursement')['meanings'], [primary])
        card = self.store.reserve('42', now=90000)[0]
        self.store.delivered(card['token'], 7)
        self.assertEqual(self.store.answer(card['token'], '42', 7, 'show', now=90001)['meanings'],
                         [primary])
        retry = self.store.save('reimbursement', 'word', '/other/', [duplicate])
        self.assertEqual(retry['status'], 'already_saved')
        self.assertEqual(retry['card']['meanings'], [primary])

    def test_distinct_domain_uses_with_same_translation_are_preserved(self):
        meanings = [
            {'definition': 'To operate a machine or vehicle.', 'translation': 'управлять',
             'example': 'She controls the crane from the cabin.'},
            {'definition': 'To direct an organisation or its activities.', 'translation': 'управлять',
             'example': 'The family controls the company.'}]
        result = self.store.save('control', 'word', '/kənˈtrəʊl/', meanings)
        self.assertEqual(result['card']['meanings'], meanings)
        self.assertEqual(self.store.lookup('control')['meanings'], meanings)

    def test_invalid_content_is_not_saved(self):
        valid = [{'definition': 'medical care', 'translation': 'лечение', 'example': 'It works.'}]
        for pronunciation, meanings in [('', valid), (None, valid), ('x' * 161, valid),
                                       ('/x/', []), ('/x/', valid * 4), ('/x/', [None]),
                                       ('/x/', [{'definition': 'missing fields'}]),
                                       ('/x/', [{**valid[0], 'example': ' '}]),
                                       ('/x/', [{**valid[0], 'translation': 'x' * 301}])]:
            with self.subTest(pronunciation=pronunciation, meanings=meanings):
                with self.assertRaises(ValueError):
                    self.store.save('invalid', 'word', pronunciation, meanings)
                self.assertIsNone(self.store.lookup('invalid'))

    def test_legacy_migration_and_enrichment_preserve_reviews(self):
        legacy_path = Path(self.tmp.name) / 'legacy.db'
        with sqlite3.connect(legacy_path) as db:
            db.execute('''CREATE TABLE cards (id INTEGER PRIMARY KEY, term TEXT NOT NULL UNIQUE,
                type TEXT NOT NULL, definition TEXT NOT NULL, translation TEXT NOT NULL,
                example TEXT NOT NULL, created_at INTEGER NOT NULL, next_review_at INTEGER NOT NULL,
                review_count INTEGER NOT NULL DEFAULT 0)''')
            db.execute("INSERT INTO cards VALUES (7,'treat','word','care','лечить','They treat it.',1,2,9)")
        with ThreadPoolExecutor(max_workers=4) as pool:
            stores = list(pool.map(lambda _: Store(legacy_path), range(4)))
        store = stores[0]
        before = store.lookup('treat')
        self.assertEqual(before['pronunciation'], '')
        self.assertEqual(before['meanings'][0]['translation'], 'лечить')
        card = store.reserve('42', now=3)[0]
        store.delivered(card['token'], 10)
        content = [{key: before[key] for key in ('definition', 'translation', 'example')}]
        duplicate = {**content[0], 'example': 'The doctor treated her.'}
        result = store.enrich('TREAT', '/triːt/', content + [duplicate])
        self.assertEqual(result['status'], 'enriched')
        self.assertEqual(result['card']['meanings'], content)
        after = Store(legacy_path).lookup('treat')
        for key in ('id', 'created_at', 'next_review_at', 'review_count'):
            self.assertEqual(after[key], before[key])
        unchanged = store.enrich('treat', '/other/', content)
        self.assertEqual(unchanged['status'], 'unchanged')
        self.assertEqual(unchanged['card'], after)
        absent = store.enrich('absent', '/x/', content)
        self.assertEqual(absent['status'], 'unchanged')
        self.assertIsNone(absent['card'])
        revealed = store.answer(card['token'], '42', 10, 'show', now=4)
        self.assertEqual(revealed['pronunciation'], '/triːt/')
        self.assertEqual(revealed['meanings'], content)

    def test_normalized_concurrent_duplicates(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            statuses = list(pool.map(self.save, ['Rule Out', ' rule  out ', 'RULE OUT', 'rule out']))
        self.assertEqual(sum(r['status'] == 'saved' for r in statuses), 1)
        self.assertEqual(self.store.lookup('RULE OUT')['term'], 'rule out')

    def test_invalid_input_not_saved(self):
        for term in ['', '  ', 'x' * 161]:
            with self.assertRaises(ValueError):
                self.save(term)

    def test_due_limit_and_no_double_delivery(self):
        for i in range(8):
            self.save(f'term {i}')
        self.assertEqual(self.store.reserve('42', now=1001), [])
        self.assertEqual(len(self.store.reserve('42', now=90000)), 5)
        self.assertEqual(len(self.store.reserve('42', now=90000)), 3)
        self.assertEqual(self.store.reserve('42', now=90001), [])

    def test_rating_requires_reveal_owner_message_and_is_idempotent(self):
        self.save()
        card = self.store.reserve('42', now=90000)[0]
        token = card['token']
        self.store.delivered(token, 7)
        self.assertIsNone(self.store.answer(token, '43', 7, 'show', now=90001))
        self.assertIsNone(self.store.answer(token, '42', 8, 'show', now=90001))
        self.assertIsNone(self.store.answer(token, '42', 7, 'good', now=90001))
        self.assertIsNotNone(self.store.answer(token, '42', 7, 'show', now=90001))
        self.assertIsNotNone(self.store.answer(token, '42', 7, 'good', now=90002))
        self.assertIsNone(self.store.answer(token, '42', 7, 'easy', now=90003))
        row = self.store.lookup('rule out')
        self.assertEqual(row['review_count'], 1)
        self.assertEqual(row['next_review_at'], 90002 + 3 * 86400)

    def test_all_intervals_and_restart(self):
        for action, days in INTERVALS.items():
            self.save(action)
            card = self.store.reserve('42', now=90000)[0]
            self.store.delivered(card['token'], 1)
            reloaded = Store(self.store.path)
            reloaded.answer(card['token'], '42', 1, 'show', now=90001)
            reloaded.answer(card['token'], '42', 1, action, now=90002)
            self.assertEqual(reloaded.lookup(action)['next_review_at'], 90002 + days * 86400)

    def test_failed_delivery_can_retry_and_old_buttons_expire(self):
        self.save()
        first = self.store.reserve('42', now=90000)[0]
        self.store.release(first['token'])
        card = self.store.reserve('42', now=90001)[0]
        self.store.delivered(card['token'], 7)
        newer = self.store.reserve('42', now=180000)[0]
        self.assertNotEqual(newer['token'], card['token'])
        self.assertIsNone(self.store.answer(card['token'], '42', 7, 'show', now=180001))


if __name__ == '__main__':
    unittest.main()
