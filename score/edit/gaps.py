from dataclasses import dataclass

from score.edit.occurrences import Occurrence


@dataclass(frozen=True)
class Gap:
    index: int
    left: str | None
    right: str | None


def enumerate_gaps(words: tuple[Occurrence, ...]) -> tuple[Gap, ...]:
    boundaries = (None, *(word.key for word in words), None)
    return tuple(
        Gap(index, left, right)
        for index, (left, right) in enumerate(zip(boundaries, boundaries[1:]))
    )
