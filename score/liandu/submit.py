import sqlite3
from dataclasses import dataclass

from score.edit.occurrences import Occurrence
from score.edit.revisions import Revision, read_current_revision, read_revision
from score.liandu.state import chars_adjacent, index_chars
from score.liandu.store import LiaisonMark, find_liaison, save_liaison


class LiaisonInvalid(ValueError):
    pass


class LiaisonConflict(LookupError):
    def __init__(self, revision: Revision, reason: str):
        super().__init__(reason)
        self.revision = revision
        self.reason = reason


class LiaisonNotFound(LookupError):
    pass


@dataclass(frozen=True)
class LiaisonSelection:
    revision: int
    voice: str
    bar: str
    left: str
    right: str


def _origin_gap(
    words: tuple[Occurrence, ...], left_key: str, right_key: str
) -> tuple[int, int]:
    """Locate the selected adjacent same-beat word seam on the origin page."""
    positions = {word.key: index for index, word in enumerate(words)}
    if left_key not in positions or right_key not in positions:
        raise LiaisonInvalid('请选择原页上存在的两个词')
    left_index, right_index = positions[left_key], positions[right_key]
    if right_index != left_index + 1:
        raise LiaisonInvalid('连读只能选择正式词序中相邻的两个词')
    if words[left_index].beat != words[right_index].beat:
        raise LiaisonInvalid('连读的两个词必须在同一拍上')
    return left_index, right_index


def submit_liaison(db: sqlite3.Connection, selection: LiaisonSelection) -> tuple[Revision, LiaisonMark]:
    with db:
        db.execute('BEGIN IMMEDIATE')
        origin = read_revision(db, selection.revision)
        location = (selection.voice, selection.bar)
        if origin is None or location not in origin.lines:
            raise LiaisonNotFound('找不到原工作版中的声部小节')
        current = read_current_revision(db, origin.score)
        if current is None:
            raise LiaisonNotFound('找不到当前正式工作版')
        origin_words = origin.line(*location)
        left_index, right_index = _origin_gap(origin_words, selection.left, selection.right)
        left_char = origin_words[left_index].chars[-1]
        right_char = origin_words[right_index].chars[0]

        current_words = current.line(*location)
        current_chars = index_chars(current_words)
        left_record = current_chars.get(left_char)
        right_record = current_chars.get(right_char)
        if left_record is None or right_record is None:
            raise LiaisonConflict(current, '原缝的字已被删换，无法办理连读')
        if not chars_adjacent(left_record, right_record):
            raise LiaisonConflict(current, '原缝已被并词或插词隔开，暂时无法办理连读')
        existing = find_liaison(
            db, current.score, selection.voice, selection.bar, left_char, right_char
        )
        if existing is not None:
            return current, existing
        mark = save_liaison(
            db, current.score, current.number, selection.voice, selection.bar, left_char, right_char
        )
        return current, mark
