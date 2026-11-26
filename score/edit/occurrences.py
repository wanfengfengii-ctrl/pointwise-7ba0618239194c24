from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class Occurrence:
    key: str
    text: str
    beat: int
    chars: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.chars:
            object.__setattr__(self, 'chars', tuple(default_char_keys(self.key, self.text)))


def default_char_keys(word_key: str, text: str) -> list[str]:
    return [f'{word_key}.{index}' for index in range(len(text))]


def make_occurrences(
    revision: int, words: Iterable[tuple[str, int]], *, offset: int = 0
) -> tuple[Occurrence, ...]:
    return tuple(
        Occurrence(f'{revision}:{ordinal}', text, beat)
        for ordinal, (text, beat) in enumerate(words, start=offset)
    )


def make_resegment_words(
    revision: int, draft: list[str], beat: int, chars: tuple[str, ...]
) -> tuple[Occurrence, ...]:
    """Build new words for a resegment while keeping the original char keys."""
    words = []
    ordinal = 0
    cursor = 0
    for text in draft:
        word_chars = chars[cursor:cursor + len(text)]
        words.append(Occurrence(f'{revision}:{ordinal}', text, beat, word_chars))
        cursor += len(text)
        ordinal += 1
    return tuple(words)
