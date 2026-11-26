from dataclasses import dataclass

from score.edit.occurrences import Occurrence
from score.liandu.store import LiaisonMark


VISIBLE = 'visible'
HIDDEN = 'hidden'
DEAD = 'dead'

STATE_LABELS = {
    VISIBLE: '可见',
    HIDDEN: '暂隐',
    DEAD: '已失效',
}


@dataclass(frozen=True)
class CharRecord:
    key: str
    text: str
    beat: int
    word_index: int
    char_index: int
    order: int


def index_chars(words: tuple[Occurrence, ...]) -> dict[str, CharRecord]:
    records = {}
    order = 0
    for word_index, word in enumerate(words):
        for char_index, (key, text) in enumerate(zip(word.chars, word.text)):
            records[key] = CharRecord(key, text, word.beat, word_index, char_index, order)
            order += 1
    return records


@dataclass(frozen=True)
class MarkState:
    mark: LiaisonMark
    state: str
    left: CharRecord | None = None
    right: CharRecord | None = None

    @property
    def visible(self) -> bool:
        return self.state == VISIBLE


def evaluate_mark(mark: LiaisonMark, words: tuple[Occurrence, ...]) -> MarkState:
    chars = index_chars(words)
    left = chars.get(mark.left)
    right = chars.get(mark.right)
    if left is None or right is None:
        return MarkState(mark, DEAD, left, right)
    # The two original chars must keep their original order and stay next to each other.
    if right.order != left.order + 1:
        return MarkState(mark, HIDDEN, left, right)
    # Adjacent inside one word: the seam is no longer a real word boundary.
    if left.word_index == right.word_index:
        return MarkState(mark, HIDDEN, left, right)
    return MarkState(mark, VISIBLE, left, right)


def evaluate_line(marks: tuple[LiaisonMark, ...], words: tuple[Occurrence, ...]) -> tuple[MarkState, ...]:
    return tuple(evaluate_mark(mark, words) for mark in marks)


def chars_adjacent(left: CharRecord, right: CharRecord) -> bool:
    """Whether two surviving chars stay next to each other in the original order."""
    return right.order == left.order + 1
