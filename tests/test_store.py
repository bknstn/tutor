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
        return self.store.save(term, 'phrasal_verb', 'exclude a possibility',
                               'исключать', 'We cannot rule out rain.', now=1000)

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
