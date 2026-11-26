import sqlite3

from score.edit.revisions import Revision, create_revision_tables, initialize_revision, read_current_revision
from score.source.bars import create_bar_table, parse_bars, required_text, write_bars
from score.source.voices import create_voice_tables, parse_voices, write_voices


class SourceImportError(ValueError):
    pass


def initialize_source_store(db: sqlite3.Connection) -> None:
    with db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('CREATE TABLE IF NOT EXISTS sources (id TEXT PRIMARY KEY, title TEXT NOT NULL)')
        create_bar_table(db)
        create_voice_tables(db)
        create_revision_tables(db)


def import_score(db: sqlite3.Connection, raw: object, *, reuse: bool = False) -> Revision:
    try:
        if not isinstance(raw, dict):
            raise ValueError('源谱必须是对象')
        score = required_text(raw.get('score'), '源谱号')
        title = required_text(raw.get('title'), '谱名')
        bars = parse_bars(raw.get('bars'))
        voices_and_lyrics = parse_voices(raw.get('voices'), bars)
    except ValueError as error:
        raise SourceImportError(str(error)) from error

    with db:
        db.execute('BEGIN IMMEDIATE')
        if read_source_title(db, score) is not None:
            if not reuse:
                raise SourceImportError(f'源谱号已经登记：{score}')
            current = read_current_revision(db, score)
            if current is None:
                raise SourceImportError(f'源谱缺少正式工作版：{score}')
            return current
        db.execute('INSERT INTO sources (id, title) VALUES (?, ?)', (score, title))
        write_bars(db, score, bars)
        write_voices(db, score, tuple(voice for voice, _ in voices_and_lyrics))
        lines = {(voice.id, bar.id): [] for voice, _ in voices_and_lyrics for bar in bars}
        for voice, words in voices_and_lyrics:
            for word in words:
                lines[voice.id, word.bar].append((word.text, word.beat))
        return initialize_revision(db, score, lines)


def read_source_title(db: sqlite3.Connection, score: str) -> str | None:
    row = db.execute('SELECT title FROM sources WHERE id = ?', (score,)).fetchone()
    return row[0] if row else None


def list_sources(db: sqlite3.Connection) -> list[tuple[str, str]]:
    return db.execute('SELECT id, title FROM sources ORDER BY id').fetchall()
