import json
import sqlite3
from dataclasses import dataclass

from score.rehearse.beat_grid import BeatCell, BeatColumn, PracticeGrid
from score.rehearse.breath_cues import BreathCue
from score.rehearse.preview import PracticePreview
from score.source.voices import Voice


@dataclass(frozen=True)
class EditionSnapshot:
    title: str
    grid: PracticeGrid
    cues: tuple[BreathCue, ...]


def create_snapshot_table(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS edition_snapshots (
            edition INTEGER PRIMARY KEY REFERENCES editions(number),
            body TEXT NOT NULL
        )
    ''')


def freeze_preview(preview: PracticePreview) -> EditionSnapshot:
    return EditionSnapshot(preview.title, preview.grid, preview.cues)


def write_snapshot(db: sqlite3.Connection, number: int, snapshot: EditionSnapshot) -> None:
    grid = snapshot.grid
    payload = {
        'title': snapshot.title,
        'columns': [[column.bar, column.beat] for column in grid.columns],
        'voices': [[voice.id, voice.name] for voice in grid.voices],
        'rows': [[list(cell.words) for cell in row] for row in grid.rows],
        'cues': [[cue.voice, cue.column] for cue in snapshot.cues],
    }
    db.execute(
        'INSERT INTO edition_snapshots (edition, body) VALUES (?, ?)',
        (number, json.dumps(payload, ensure_ascii=False)),
    )


def read_snapshot(db: sqlite3.Connection, number: int) -> EditionSnapshot | None:
    row = db.execute('SELECT body FROM edition_snapshots WHERE edition = ?', (number,)).fetchone()
    if row is None:
        return None
    payload = json.loads(row[0])
    grid = PracticeGrid(
        tuple(BeatColumn(*column) for column in payload['columns']),
        tuple(Voice(*voice) for voice in payload['voices']),
        tuple(tuple(BeatCell(tuple(words)) for words in line) for line in payload['rows']),
    )
    return EditionSnapshot(payload['title'], grid, tuple(BreathCue(*cue) for cue in payload['cues']))
