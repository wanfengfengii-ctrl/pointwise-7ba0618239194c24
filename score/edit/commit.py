import sqlite3
from dataclasses import dataclass

from score.edit.gaps import enumerate_gaps
from score.edit.measure_edit import apply_insertion, apply_replacement
from score.edit.occurrences import Occurrence
from score.edit.revisions import Revision, read_current_revision, read_revision, reserve_revision_number, save_revision


class InvalidEdit(ValueError):
    pass


class EditNotFound(LookupError):
    pass


@dataclass(frozen=True)
class EditSelection:
    revision: int
    voice: str
    bar: str
    kind: str
    first: str | None
    last: str | None


@dataclass(frozen=True)
class SavedEdit:
    revision: Revision
    selection: EditSelection
    words: tuple[Occurrence, ...]


@dataclass(frozen=True)
class EditConflict:
    revision: Revision
    selection: EditSelection
    words: tuple[Occurrence, ...]
    start: int
    stop: int
    reason: str


def _gap_index(words: tuple[Occurrence, ...], left: str | None, right: str | None) -> int | None:
    for gap in enumerate_gaps(words):
        if (gap.left, gap.right) == (left, right):
            return gap.index
    return None


def _origin_bounds(selection: EditSelection, words: tuple[Occurrence, ...]) -> tuple[int, int]:
    if selection.kind == 'insert':
        index = _gap_index(words, selection.first, selection.last)
        if index is not None:
            return index, index
        raise InvalidEdit('请选择原页上的一条缝')
    positions = {word.key: i for i, word in enumerate(words)}
    start = positions.get(selection.first)
    end = positions.get(selection.last)
    if start is None or end is None or start > end:
        raise InvalidEdit('请选择原页中正序排列的一段连续歌词')
    return start, end + 1


def _replacement_index(words: tuple[Occurrence, ...], selected: tuple[Occurrence, ...]) -> int | None:
    wanted = tuple(word.key for word in selected)
    for index, word in enumerate(words):
        if word.key == wanted[0]:
            found = tuple(item.key for item in words[index:index + len(wanted)])
            return index if found == wanted else None
    return None


def _conflict_bounds(
    old: tuple[Occurrence, ...], now: tuple[Occurrence, ...], start: int, stop: int
) -> tuple[int, int]:
    positions = {word.key: i for i, word in enumerate(now)}
    # When the original endpoints survive, point to the first blocked inner gap.
    selected = old[start:stop]
    if selected and all(word.key in positions for word in selected):
        for left, right in zip(selected, selected[1:]):
            low, high = positions[left.key] + 1, positions[right.key]
            if low < high:
                return low, high
    low = next((positions[word.key] + 1 for word in reversed(old[:start]) if word.key in positions), 0)
    high = next((positions[word.key] for word in old[stop:] if word.key in positions), len(now))
    return low, high


def submit_edit(db: sqlite3.Connection, selection: EditSelection, draft: str) -> SavedEdit | EditConflict:
    if selection.kind not in ('replace', 'insert'):
        raise InvalidEdit('未知编辑方式')
    lyrics = draft.split()
    if selection.kind == 'insert' and not lyrics:
        raise InvalidEdit('插入请至少填一个词')

    with db:
        db.execute('BEGIN IMMEDIATE')
        origin = read_revision(db, selection.revision)
        location = (selection.voice, selection.bar)
        if origin is None or location not in origin.lines:
            raise EditNotFound('找不到原工作版中的声部小节')
        current = read_current_revision(db, origin.score)
        if current is None:
            raise EditNotFound('找不到当前正式工作版')
        old_words = origin.line(*location)
        current_words = current.line(*location)
        start, stop = _origin_bounds(selection, old_words)
        if selection.kind == 'insert':
            index = _gap_index(current_words, selection.first, selection.last)
            reason = '原缝的邻词已改变'
        else:
            index = _replacement_index(current_words, old_words[start:stop])
            reason = '原词段已改变或段内已有新词'
        if index is None:
            low, high = _conflict_bounds(old_words, current_words, start, stop)
            return EditConflict(current, selection, current_words, low, high, reason)

        number = reserve_revision_number(db)
        if selection.kind == 'insert':
            edited = apply_insertion(current_words, index, lyrics, number)
        else:
            edited = apply_replacement(current_words, index, index + stop - start, lyrics, number)
        lines = dict(current.lines)
        lines[location] = edited
        revision = Revision(number, current.score, lines)
        save_revision(db, revision)
        return SavedEdit(revision, selection, edited)
