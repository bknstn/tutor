"""Small, single-user vocabulary store. All dates are UTC epoch seconds."""
import os
import secrets
import sqlite3
import time
import unicodedata
from contextlib import contextmanager
from pathlib import Path

TYPES = ('word', 'phrase', 'phrasal_verb', 'idiom')
INTERVALS = {'again': 1, 'good': 3, 'easy': 7}


def normalize(term):
    if not isinstance(term, str):
        raise ValueError('term must be text')
    term = ' '.join(unicodedata.normalize('NFKC', term).split())
    if not term or len(term) > 160 or len(term.split()) > 12:
        raise ValueError('Send one word or short phrase (up to 12 words).')
    return term.casefold()


class Store:
    def __init__(self, path=None):
        self.path = Path(path) if path else Path(os.environ['HERMES_HOME']) / 'plugin-data/hermes-tutor/data.db'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS cards (
                    id INTEGER PRIMARY KEY, term TEXT NOT NULL UNIQUE,
                    type TEXT NOT NULL CHECK(type IN ('word','phrase','phrasal_verb','idiom')),
                    definition TEXT NOT NULL, translation TEXT NOT NULL, example TEXT NOT NULL,
                    created_at INTEGER NOT NULL, next_review_at INTEGER NOT NULL,
                    review_count INTEGER NOT NULL DEFAULT 0);
                CREATE INDEX IF NOT EXISTS cards_due ON cards(next_review_at);
                CREATE TABLE IF NOT EXISTS reviews (
                    token TEXT PRIMARY KEY, card_id INTEGER NOT NULL REFERENCES cards(id),
                    chat_id TEXT NOT NULL, created_at INTEGER NOT NULL,
                    message_id INTEGER, revealed INTEGER NOT NULL DEFAULT 0,
                    answered_at INTEGER);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def lookup(self, term):
        with self.connect() as db:
            row = db.execute('SELECT * FROM cards WHERE term=?', (normalize(term),)).fetchone()
            return dict(row) if row else None

    def save(self, term, type, definition, translation, example, now=None):
        term = normalize(term)
        if type not in TYPES:
            raise ValueError('Invalid card type')
        for value in (definition, translation, example):
            if not isinstance(value, str) or not value.strip() or len(value) > 700:
                raise ValueError('Card fields must contain 1–700 characters')
        now = int(time.time() if now is None else now)
        with self.connect() as db:
            result = db.execute('''INSERT INTO cards
                (term,type,definition,translation,example,created_at,next_review_at)
                VALUES (?,?,?,?,?,?,?) ON CONFLICT(term) DO NOTHING''',
                (term, type, definition.strip(), translation.strip(), example.strip(), now, now + 86400))
            return {'status': 'saved' if result.rowcount else 'already_saved', 'term': term}

    def reserve(self, chat_id, limit=5, now=None):
        now = int(time.time() if now is None else now)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            rows = db.execute('''SELECT * FROM cards WHERE next_review_at<=?
                AND NOT EXISTS (SELECT 1 FROM reviews r WHERE r.card_id=cards.id
                    AND r.created_at>?) ORDER BY next_review_at,id LIMIT ?''',
                (now, now - 20 * 3600, min(5, max(1, limit)))).fetchall()
            result = []
            for row in rows:
                token = secrets.token_hex(8)
                db.execute('INSERT INTO reviews(token,card_id,chat_id,created_at) VALUES (?,?,?,?)',
                           (token, row['id'], str(chat_id), now))
                result.append({**dict(row), 'token': token})
            return result

    def delivered(self, token, message_id):
        with self.connect() as db:
            db.execute('UPDATE reviews SET message_id=? WHERE token=?', (message_id, token))

    def release(self, token):
        with self.connect() as db:
            db.execute('DELETE FROM reviews WHERE token=? AND message_id IS NULL', (token,))

    def answer(self, token, chat_id, message_id, action, now=None):
        if action not in ('show', *INTERVALS):
            raise ValueError('Unknown action')
        now = int(time.time() if now is None else now)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('''SELECT r.*, c.term,c.definition,c.translation,c.example
                FROM reviews r JOIN cards c ON c.id=r.card_id
                WHERE token=? AND chat_id=? AND message_id=? AND answered_at IS NULL
                AND r.created_at>? AND NOT EXISTS (SELECT 1 FROM reviews newer
                    WHERE newer.card_id=r.card_id AND newer.created_at>r.created_at)''',
                (token, str(chat_id), message_id, now - 7 * 86400)).fetchone()
            if not row:
                return None
            if action == 'show':
                db.execute('UPDATE reviews SET revealed=1 WHERE token=?', (token,))
            else:
                if not row['revealed']:
                    return None
                db.execute('UPDATE reviews SET answered_at=? WHERE token=?', (now, token))
                db.execute('UPDATE cards SET review_count=review_count+1,next_review_at=? WHERE id=?',
                           (now + INTERVALS[action] * 86400, row['card_id']))
            return dict(row)
