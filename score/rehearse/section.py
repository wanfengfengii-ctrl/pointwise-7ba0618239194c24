from dataclasses import dataclass

from score.source.bars import Bar


class InvalidPracticeRange(ValueError):
    pass


@dataclass(frozen=True)
class PracticeSection:
    bars: tuple[Bar, ...]

    @property
    def first(self) -> str:
        return self.bars[0].id

    @property
    def last(self) -> str:
        return self.bars[-1].id


def resolve_section(bars: tuple[Bar, ...], first: str, last: str) -> PracticeSection:
    positions = {bar.id: index for index, bar in enumerate(bars)}
    if first not in positions or last not in positions:
        raise InvalidPracticeRange('排练范围包含不存在的小节')
    start, end = positions[first], positions[last]
    if start > end:
        raise InvalidPracticeRange('尾小节必须位于首小节之后或与其相同')
    return PracticeSection(bars[start:end + 1])
