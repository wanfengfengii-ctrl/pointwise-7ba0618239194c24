from score.edit.occurrences import Occurrence


def project_voice_line(words: tuple[Occurrence, ...], beats: int) -> tuple[tuple[str, ...], ...]:
    cells: list[list[str]] = [[] for _ in range(beats)]
    for word in words:
        cells[word.beat].append(word.text)
    return tuple(tuple(cell) for cell in cells)
