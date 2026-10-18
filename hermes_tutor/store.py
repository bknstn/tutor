"""Small, single-user vocabulary store. All dates are UTC epoch seconds."""
import json
import os
import secrets
import sqlite3
import time
import unicodedata
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TYPES = ('word', 'phrase', 'phrasal_verb', 'idiom')
INTERVALS = {'again': 1, 'good': 3, 'easy': 7}
REVIEW_LIMIT = 10
REVIEW_LIFETIME = 20 * 3600


def card_data(row):
    card = dict(row)
    card['meanings'] = json.loads(card['meanings']) or [
        {key: card[key] for key in ('definition', 'translation', 'example')}]
    return card


def validate_content(pronunciation, meanings):
    if not isinstance(pronunciation, str) or not pronunciation.strip() or len(pronunciation) > 160:
        raise ValueError('Provide an IPA pronunciation (1–160 characters)')
    if not isinstance(meanings, list) or not 1 <= len(meanings) <= 3:
        raise ValueError('Provide 1–3 meanings; each extra meaning must add a new sense or domain-specific use')
    cleaned = []
    definitions = set()
    for meaning in meanings:
        if not isinstance(meaning, dict) or set(meaning) != {'definition', 'translation', 'example'}:
            raise ValueError('Each meaning needs definition, translation, and example')
        for value in meaning.values():
            if not isinstance(value, str) or not value.strip() or len(value) > 300:
                raise ValueError('Meaning fields must contain 1–300 characters')
        content = {key: value.strip() for key, value in meaning.items()}
        # Catch repeated definitions deterministically. Semantic paraphrases must
        # be merged by the tutor before saving; text similarity cannot establish
        # whether two senses or domain-specific uses are actually distinct.
        definition = ' '.join(''.join(
            char if char.isalnum() else ' '
            for char in unicodedata.normalize('NFKC', content['definition']).casefold()).split())
        if definition not in definitions:
            definitions.add(definition)
            cleaned.append(content)
    return pronunciation.strip(), cleaned


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
                CREATE TABLE IF NOT EXISTS review_batches (
                    token TEXT PRIMARY KEY, chat_id TEXT NOT NULL,
                    created_at INTEGER NOT NULL, message_id INTEGER,
                    state TEXT NOT NULL DEFAULT 'active', revision INTEGER NOT NULL DEFAULT 0,
                    total INTEGER NOT NULL CHECK(total BETWEEN 1 AND 10),
                    parent_token TEXT UNIQUE REFERENCES review_batches(token));
                CREATE INDEX IF NOT EXISTS review_batches_chat ON review_batches(chat_id,state);
                CREATE UNIQUE INDEX IF NOT EXISTS review_batches_active ON review_batches(chat_id)
                    WHERE state='active';
                CREATE TABLE IF NOT EXISTS review_items (
                    batch_token TEXT NOT NULL REFERENCES review_batches(token),
                    position INTEGER NOT NULL, review_token TEXT NOT NULL UNIQUE REFERENCES reviews(token),
                    PRIMARY KEY(batch_token,position));
                CREATE TABLE IF NOT EXISTS scheduled_reviews (
                    chat_id TEXT NOT NULL, day TEXT NOT NULL,
                    batch_token TEXT REFERENCES review_batches(token), PRIMARY KEY(chat_id,day));
            ''')
            # Migrate existing cards without changing IDs or review history.
            db.execute('BEGIN IMMEDIATE')
            columns = {row['name'] for row in db.execute('PRAGMA table_info(cards)')}
            for name, default in (('pronunciation', ''), ('meanings', '[]')):
                if name not in columns:
                    db.execute(f"ALTER TABLE cards ADD COLUMN {name} TEXT NOT NULL DEFAULT '{default}'")

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
            return card_data(row) if row else None

    def save(self, term, type, pronunciation, meanings, now=None):
        term = normalize(term)
        if type not in TYPES:
            raise ValueError('Invalid card type')
        pronunciation, meanings = validate_content(pronunciation, meanings)
        primary = meanings[0]
        now = int(time.time() if now is None else now)
        with self.connect() as db:
            result = db.execute('''INSERT INTO cards
                (term,type,definition,translation,example,pronunciation,meanings,created_at,next_review_at)
                VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(term) DO NOTHING''',
                (term, type, primary['definition'], primary['translation'], primary['example'],
                 pronunciation, json.dumps(meanings, ensure_ascii=False), now, now + 86400))
            row = db.execute('SELECT * FROM cards WHERE term=?', (term,)).fetchone()
            return {'status': 'saved' if result.rowcount else 'already_saved',
                    'term': term, 'card': card_data(row)}

    def enrich(self, term, pronunciation, meanings):
        term = normalize(term)
        pronunciation, meanings = validate_content(pronunciation, meanings)
        primary = meanings[0]
        with self.connect() as db:
            result = db.execute('''UPDATE cards SET pronunciation=?,meanings=?,
                definition=?,translation=?,example=? WHERE term=? AND pronunciation='' ''',
                (pronunciation, json.dumps(meanings, ensure_ascii=False), primary['definition'],
                 primary['translation'], primary['example'], term))
            row = db.execute('SELECT * FROM cards WHERE term=?', (term,)).fetchone()
            return {'status': 'enriched' if result.rowcount else 'unchanged',
                    'term': term, 'card': card_data(row) if row else None}

    def reserve(self, chat_id, limit=5, now=None):
        """Legacy individual-card reservations; new deliveries use start_review."""
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
                result.append({**card_data(row), 'token': token})
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
            row = db.execute('''SELECT r.*, c.term,c.definition,c.translation,c.example,c.pronunciation,c.meanings
                FROM reviews r JOIN cards c ON c.id=r.card_id
                WHERE token=? AND chat_id=? AND message_id=? AND answered_at IS NULL
                AND NOT EXISTS (SELECT 1 FROM review_items i WHERE i.review_token=r.token)
                AND r.created_at>? AND NOT EXISTS (SELECT 1 FROM reviews newer
                    WHERE newer.card_id=r.card_id AND (newer.created_at>r.created_at
                        OR (newer.created_at=r.created_at AND newer.rowid>r.rowid)))''',
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
            return card_data(row)

    def _due_reviews(self, db, now):
        return db.execute('''SELECT c.* FROM cards c WHERE c.next_review_at<=?
            AND NOT EXISTS (SELECT 1 FROM reviews r
                LEFT JOIN review_items i ON i.review_token=r.token
                LEFT JOIN review_batches b ON b.token=i.batch_token
                WHERE r.card_id=c.id AND r.created_at>?
                AND (b.token IS NULL OR b.state='active'))
            ORDER BY c.next_review_at,c.id LIMIT ?''',
            (now, now - REVIEW_LIFETIME, REVIEW_LIMIT)).fetchall()

    def _review_view(self, db, token, now):
        batch = dict(db.execute('SELECT * FROM review_batches WHERE token=?', (token,)).fetchone())
        batch['done'] = db.execute('''SELECT COUNT(*) FROM review_items i
            JOIN reviews r ON r.token=i.review_token WHERE i.batch_token=?
            AND r.answered_at IS NOT NULL''', (token,)).fetchone()[0]
        row = db.execute('''SELECT c.*,r.revealed,r.token AS review_token FROM review_items i
            JOIN reviews r ON r.token=i.review_token JOIN cards c ON c.id=r.card_id
            WHERE i.batch_token=? AND r.answered_at IS NULL ORDER BY i.position LIMIT 1''',
            (token,)).fetchone() if batch['state'] == 'active' else None
        batch['card'] = card_data(row) if row else None
        # Only the next bounded batch matters for the consent prompt.
        batch['more'] = len(self._due_reviews(db, now)) if batch['state'] == 'complete' else 0
        return batch

    def _create_review(self, db, chat_id, now, parent=None, message_id=None):
        cards = self._due_reviews(db, now)
        if not cards:
            return None
        token = secrets.token_hex(8)
        db.execute('''INSERT INTO review_batches
            (token,chat_id,created_at,total,parent_token,message_id) VALUES (?,?,?,?,?,?)''',
            (token, str(chat_id), now, len(cards), parent, message_id))
        for position, card in enumerate(cards):
            review_token = secrets.token_hex(8)
            db.execute('''INSERT INTO reviews(token,card_id,chat_id,created_at,message_id)
                VALUES (?,?,?,?,?)''', (review_token, card['id'], str(chat_id), now, message_id))
            db.execute('INSERT INTO review_items VALUES (?,?,?)', (token, position, review_token))
        return self._review_view(db, token, now)

    def start_review(self, chat_id, scheduled=False, now=None):
        """Claim at most ten cards, once per scheduled Warsaw day or by explicit request."""
        now = int(time.time() if now is None else now)
        chat_id = str(chat_id)
        day = datetime.fromtimestamp(now, ZoneInfo('Europe/Warsaw')).date().isoformat()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('''UPDATE review_batches SET state='expired',revision=revision+1
                WHERE chat_id=? AND state IN ('active','complete') AND created_at<=?''',
                (chat_id, now - REVIEW_LIFETIME))
            if scheduled and db.execute('SELECT 1 FROM scheduled_reviews WHERE chat_id=? AND day=?',
                                        (chat_id, day)).fetchone():
                return None
            active = db.execute("SELECT token FROM review_batches WHERE chat_id=? AND state='active'",
                                (chat_id,)).fetchone()
            batch = self._review_view(db, active['token'], now) if active else self._create_review(db, chat_id, now)
            if scheduled:
                db.execute('INSERT INTO scheduled_reviews VALUES (?,?,?)',
                           (chat_id, day, batch['token'] if batch else None))
            if batch:
                batch['created'] = not bool(active)
            return batch

    def deliver_review(self, token, message_id):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            result = db.execute('''UPDATE review_batches SET message_id=?
                WHERE token=? AND message_id IS NULL AND state='active' ''', (message_id, token))
            if result.rowcount != 1:
                raise ValueError('Review delivery is no longer current')
            db.execute('''UPDATE reviews SET message_id=? WHERE token IN
                (SELECT review_token FROM review_items WHERE batch_token=?)''', (message_id, token))

    def abandon_review(self, token):
        """Release an unbound failed delivery; any orphaned Telegram buttons stay inactive."""
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            result = db.execute("UPDATE review_batches SET state='failed' WHERE token=? AND message_id IS NULL",
                                (token,))
            if result.rowcount:
                db.execute('DELETE FROM scheduled_reviews WHERE batch_token=?', (token,))

    def review_action(self, token, revision, chat_id, message_id, action, now=None):
        """Advance one bound panel atomically. Stale clicks only restore its current view."""
        if action not in ('show', 'more', 'stop', *INTERVALS):
            raise ValueError('Unknown review action')
        now = int(time.time() if now is None else now)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('''SELECT * FROM review_batches WHERE token=? AND chat_id=?
                AND message_id=? AND created_at>? AND state NOT IN ('failed','expired')''',
                (token, str(chat_id), message_id, now - REVIEW_LIFETIME)).fetchone()
            if not row:
                return None
            if row['state'] == 'continued':
                # A retried consent click must restore the child, never create another batch.
                child = db.execute('''SELECT token FROM review_batches WHERE chat_id=? AND message_id=?
                    AND created_at>? AND state IN ('active','complete','stopped')
                    ORDER BY rowid DESC LIMIT 1''',
                    (str(chat_id), message_id, now - REVIEW_LIFETIME)).fetchone()
                return self._review_view(db, child['token'], now) if child else None
            view = self._review_view(db, token, now)
            if row['revision'] != revision or row['state'] == 'stopped':
                return view
            if action == 'stop':
                db.execute("UPDATE review_batches SET state='stopped',revision=revision+1 WHERE token=?", (token,))
            elif action == 'more' and row['state'] == 'complete':
                if db.execute("SELECT 1 FROM review_batches WHERE chat_id=? AND state='active' AND created_at>?",
                              (str(chat_id), now - REVIEW_LIFETIME)).fetchone():
                    return None
                child = self._create_review(db, chat_id, now, parent=token, message_id=message_id)
                if child:
                    db.execute("UPDATE review_batches SET state='continued',revision=revision+1 WHERE token=?", (token,))
                    return child
            elif row['state'] == 'active' and view['card']:
                card = view['card']
                if action == 'show':
                    db.execute('UPDATE reviews SET revealed=1 WHERE token=?', (card['review_token'],))
                elif action in INTERVALS and card['revealed']:
                    db.execute('UPDATE reviews SET answered_at=? WHERE token=?', (now, card['review_token']))
                    db.execute('UPDATE cards SET review_count=review_count+1,next_review_at=? WHERE id=?',
                               (now + INTERVALS[action] * 86400, card['id']))
                    if view['done'] + 1 == view['total']:
                        db.execute("UPDATE review_batches SET state='complete' WHERE token=?", (token,))
                else:
                    return view
                db.execute('UPDATE review_batches SET revision=revision+1 WHERE token=?', (token,))
            return self._review_view(db, token, now)
