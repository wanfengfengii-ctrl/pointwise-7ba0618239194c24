import sqlite3
from dataclasses import dataclass

from score.source.meter import Meter


@dataclass(frozen=True)
class Bar:
    id: str
    meter: Meter


def required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{label}必须是非空文字')
    return value.strip()


def parse_bars(raw: object) -> tuple[Bar, ...]:
    if not isinstance(raw, list) or not raw:
        raise ValueError('源谱必须包含小节')
    bars = []
    seen = set()
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError('小节条目必须是对象')
        bar_id = required_text(entry.get('id'), '小节号')
        if bar_id in seen:
            raise ValueError(f'小节号重复：{bar_id}')
        bars.append(Bar(bar_id, Meter(entry.get('beats'))))
        seen.add(bar_id)
    return tuple(bars)


def create_bar_table(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS bars (
            score TEXT NOT NULL REFERENCES sources(id),
            bar TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            beats INTEGER NOT NULL CHECK (beats > 0),
            PRIMARY KEY (score, bar),
            UNIQUE (score, ordinal)
        )
    ''')


def write_bars(db: sqlite3.Connection, score: str, bars: tuple[Bar, ...]) -> None:
    db.executemany(
        'INSERT INTO bars (score, bar, ordinal, beats) VALUES (?, ?, ?, ?)',
        [(score, bar.id, i, bar.meter.beats) for i, bar in enumerate(bars)],
    )


def read_bars(db: sqlite3.Connection, score: str) -> tuple[Bar, ...]:
    rows = db.execute('SELECT bar, beats FROM bars WHERE score = ? ORDER BY ordinal', (score,))
    return tuple(Bar(bar_id, Meter(beats)) for bar_id, beats in rows)
