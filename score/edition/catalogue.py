import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogueEntry:
    number: int
    revision: int
    first: str
    last: str


def create_catalogue_table(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS editions (
            number INTEGER PRIMARY KEY,
            revision INTEGER NOT NULL REFERENCES revisions(number),
            first_bar TEXT NOT NULL,
            last_bar TEXT NOT NULL
        )
    ''')


def register_edition(db: sqlite3.Connection, revision: int, first: str, last: str) -> CatalogueEntry:
    cursor = db.execute(
        'INSERT INTO editions (revision, first_bar, last_bar) VALUES (?, ?, ?)', (revision, first, last)
    )
    return CatalogueEntry(cursor.lastrowid, revision, first, last)


def find_edition(db: sqlite3.Connection, number: int) -> CatalogueEntry | None:
    row = db.execute(
        'SELECT number, revision, first_bar, last_bar FROM editions WHERE number = ?', (number,)
    ).fetchone()
    return CatalogueEntry(*row) if row else None


def list_editions(db: sqlite3.Connection) -> tuple[CatalogueEntry, ...]:
    rows = db.execute('SELECT number, revision, first_bar, last_bar FROM editions ORDER BY number DESC')
    return tuple(CatalogueEntry(*row) for row in rows)
