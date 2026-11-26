import sqlite3
from dataclasses import dataclass

from score.source.bars import Bar, required_text
from score.source.meter import validate_beat


@dataclass(frozen=True)
class Voice:
    id: str
    name: str


@dataclass(frozen=True)
class SourceLyric:
    bar: str
    text: str
    beat: int


def parse_voices(raw: object, bars: tuple[Bar, ...]) -> tuple[tuple[Voice, tuple[SourceLyric, ...]], ...]:
    if not isinstance(raw, list) or not raw:
        raise ValueError('源谱必须包含声部')
    meters = {bar.id: bar.meter for bar in bars}
    seen = set()
    voices = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError('声部条目必须是对象')
        voice = Voice(required_text(entry.get('id'), '声部号'), required_text(entry.get('name'), '声部名称'))
        if voice.id in seen:
            raise ValueError(f'声部号重复：{voice.id}')
        lyrics = entry.get('lyrics')
        if not isinstance(lyrics, list):
            raise ValueError('声部歌词必须是数组')
        words = []
        for lyric in lyrics:
            if not isinstance(lyric, dict):
                raise ValueError('歌词条目必须是对象')
            bar = required_text(lyric.get('bar'), '词条小节号')
            if bar not in meters:
                raise ValueError(f'词条小节不存在：{bar}')
            text = required_text(lyric.get('text'), '歌词')
            if len(text.split()) != 1:
                raise ValueError('每个歌词条目只能登记一个词')
            words.append(SourceLyric(bar, text, validate_beat(meters[bar], lyric.get('beat'))))
        voices.append((voice, tuple(words)))
        seen.add(voice.id)
    return tuple(voices)


def create_voice_tables(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS voices (
            score TEXT NOT NULL REFERENCES sources(id),
            voice TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            name TEXT NOT NULL,
            PRIMARY KEY (score, voice),
            UNIQUE (score, ordinal)
        )
    ''')


def write_voices(db: sqlite3.Connection, score: str, voices: tuple[Voice, ...]) -> None:
    db.executemany(
        'INSERT INTO voices (score, voice, ordinal, name) VALUES (?, ?, ?, ?)',
        [(score, voice.id, i, voice.name) for i, voice in enumerate(voices)],
    )


def read_voices(db: sqlite3.Connection, score: str) -> tuple[Voice, ...]:
    rows = db.execute('SELECT voice, name FROM voices WHERE score = ? ORDER BY ordinal', (score,))
    return tuple(Voice(voice_id, name) for voice_id, name in rows)
