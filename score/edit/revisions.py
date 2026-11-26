import json
import sqlite3
from dataclasses import dataclass

from score.edit.occurrences import Occurrence, make_occurrences


@dataclass(frozen=True)
class Revision:
    number: int
    score: str
    lines: dict[tuple[str, str], tuple[Occurrence, ...]]

    def line(self, voice: str, bar: str) -> tuple[Occurrence, ...]:
        return self.lines[voice, bar]


def create_revision_tables(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS revisions (
            number INTEGER PRIMARY KEY,
            score TEXT NOT NULL REFERENCES sources(id),
            body TEXT NOT NULL,
            UNIQUE (score, number)
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS current_revisions (
            score TEXT PRIMARY KEY REFERENCES sources(id),
            revision INTEGER NOT NULL,
            FOREIGN KEY (score, revision) REFERENCES revisions(score, number)
        )
    ''')


def reserve_revision_number(db: sqlite3.Connection) -> int:
    """Choose the next number while the caller holds the write transaction."""
    row = db.execute('SELECT COALESCE(MAX(number), 0) + 1 FROM revisions').fetchone()
    return row[0]


def save_revision(db: sqlite3.Connection, revision: Revision) -> None:
    body = [
        [voice, bar, [[word.key, word.text, word.beat] for word in words]]
        for (voice, bar), words in revision.lines.items()
    ]
    db.execute(
        'INSERT INTO revisions (number, score, body) VALUES (?, ?, ?)',
        (revision.number, revision.score, json.dumps(body, ensure_ascii=False)),
    )
    db.execute('''
        INSERT INTO current_revisions (score, revision) VALUES (?, ?)
        ON CONFLICT(score) DO UPDATE SET revision = excluded.revision
    ''', (revision.score, revision.number))


def initialize_revision(
    db: sqlite3.Connection, score: str, raw_lines: dict[tuple[str, str], list[tuple[str, int]]]
) -> Revision:
    number = reserve_revision_number(db)
    lines = {}
    offset = 0
    for location, words in raw_lines.items():
        lines[location] = make_occurrences(number, words, offset=offset)
        offset += len(words)
    revision = Revision(number, score, lines)
    save_revision(db, revision)
    return revision


def _decode_revision(row: tuple | None) -> Revision | None:
    if row is None:
        return None
    number, score, body = row
    lines = {
        (voice, bar): tuple(Occurrence(*word) for word in words)
        for voice, bar, words in json.loads(body)
    }
    return Revision(number, score, lines)


def read_revision(db: sqlite3.Connection, number: int) -> Revision | None:
    row = db.execute('SELECT number, score, body FROM revisions WHERE number = ?', (number,)).fetchone()
    return _decode_revision(row)


def read_current_revision(db: sqlite3.Connection, score: str) -> Revision | None:
    row = db.execute('''
        SELECT r.number, r.score, r.body
        FROM current_revisions AS c JOIN revisions AS r ON r.number = c.revision
        WHERE c.score = ?
    ''', (score,)).fetchone()
    return _decode_revision(row)
