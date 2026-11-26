from dataclasses import dataclass

from score.rehearse.beat_grid import PracticeGrid


@dataclass(frozen=True)
class BreathCue:
    voice: str
    column: int


def place_breath_cues(grid: PracticeGrid) -> tuple[BreathCue, ...]:
    cues = []
    # Visit each shared beat first so cues at that beat follow the voice order.
    for column in range(len(grid.columns) - 1):
        for voice, row in zip(grid.voices, grid.rows):
            if not row[column].words and row[column + 1].words:
                cues.append(BreathCue(voice.id, column))
    return tuple(cues)
