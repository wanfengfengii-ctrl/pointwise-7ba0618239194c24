import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class LiaisonMark:
    id: int
    score: str
    revision: int
    voice: str
    bar: str
    left: str
    right: str


def create_liaison_table(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS liaisons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            score TEXT NOT NULL REFERENCES sources(id),
            revision INTEGER NOT NULL,
            voice TEXT NOT NULL,
            bar TEXT NOT NULL,
            left_char TEXT NOT NULL,
            right_char TEXT NOT NULL
        )
    ''')
    db.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_liaisons_seam
        ON liaisons (score, voice, bar, left_char, right_char)
    ''')


def initialize_liaison_store(db: sqlite3.Connection) -> None:
    with db:
        db.execute('BEGIN IMMEDIATE')
        create_liaison_table(db)


def save_liaison(
    db: sqlite3.Connection, score: str, revision: int, voice: str, bar: str, left: str, right: str
) -> LiaisonMark:
    cursor = db.execute(
        '''
        INSERT INTO liaisons (score, revision, voice, bar, left_char, right_char)
        VALUES (?, ?, ?, ?, ?, ?)
        ''',
        (score, revision, voice, bar, left, right),
    )
    return LiaisonMark(cursor.lastrowid, score, revision, voice, bar, left, right)


def read_liaisons(db: sqlite3.Connection, score: str, voice: str, bar: str) -> tuple[LiaisonMark, ...]:
    rows = db.execute(
        'SELECT id, score, revision, voice, bar, left_char, right_char FROM liaisons '
        'WHERE score = ? AND voice = ? AND bar = ? ORDER BY id',
        (score, voice, bar),
    ).fetchall()
    return tuple(LiaisonMark(*row) for row in rows)


def find_liaison(
    db: sqlite3.Connection, score: str, voice: str, bar: str, left: str, right: str
) -> LiaisonMark | None:
    row = db.execute(
        'SELECT id, score, revision, voice, bar, left_char, right_char FROM liaisons '
        'WHERE score = ? AND voice = ? AND bar = ? AND left_char = ? AND right_char = ? ORDER BY id',
        (score, voice, bar, left, right),
    ).fetchone()
    return LiaisonMark(*row) if row else None
