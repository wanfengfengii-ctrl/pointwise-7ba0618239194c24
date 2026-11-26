from dataclasses import dataclass

from score.edit.revisions import Revision
from score.rehearse.section import PracticeSection
from score.rehearse.voice_lines import project_voice_line
from score.source.voices import Voice


@dataclass(frozen=True)
class BeatColumn:
    bar: str
    beat: int


@dataclass(frozen=True)
class BeatCell:
    words: tuple[str, ...]


@dataclass(frozen=True)
class PracticeGrid:
    columns: tuple[BeatColumn, ...]
    voices: tuple[Voice, ...]
    rows: tuple[tuple[BeatCell, ...], ...]


def build_beat_grid(revision: Revision, section: PracticeSection, voices: tuple[Voice, ...]) -> PracticeGrid:
    columns = tuple(BeatColumn(bar.id, beat) for bar in section.bars for beat in bar.meter.positions())
    rows = []
    for voice in voices:
        cells = []
        for bar in section.bars:
            projected = project_voice_line(revision.line(voice.id, bar.id), bar.meter.beats)
            cells.extend(BeatCell(words) for words in projected)
        rows.append(tuple(cells))
    return PracticeGrid(columns, voices, tuple(rows))
