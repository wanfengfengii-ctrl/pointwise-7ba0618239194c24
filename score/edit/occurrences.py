from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class Occurrence:
    key: str
    text: str
    beat: int


def make_occurrences(
    revision: int, words: Iterable[tuple[str, int]], *, offset: int = 0
) -> tuple[Occurrence, ...]:
    return tuple(
        Occurrence(f'{revision}:{ordinal}', text, beat)
        for ordinal, (text, beat) in enumerate(words, start=offset)
    )
