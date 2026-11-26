from score.edit.occurrences import Occurrence, make_occurrences


def apply_replacement(
    words: tuple[Occurrence, ...], start: int, stop: int, lyrics: list[str], revision: int
) -> tuple[Occurrence, ...]:
    beat = words[start].beat
    written = make_occurrences(revision, ((text, beat) for text in lyrics))
    return words[:start] + written + words[stop:]


def apply_insertion(
    words: tuple[Occurrence, ...], index: int, lyrics: list[str], revision: int
) -> tuple[Occurrence, ...]:
    beat = 0
    if words:
        neighbor = index - 1 if index else 0
        beat = words[neighbor].beat
    written = make_occurrences(revision, ((text, beat) for text in lyrics))
    return words[:index] + written + words[index:]
