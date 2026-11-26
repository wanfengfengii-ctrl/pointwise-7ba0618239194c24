from score.edit.occurrences import Occurrence, make_resegment_words


class ResegmentInvalid(ValueError):
    pass


def validate_segment(words: tuple[Occurrence, ...], start: int, stop: int) -> None:
    """A resegment picks a non-empty span whose words all share one beat."""
    if start < 0 or stop <= start or stop > len(words):
        raise ResegmentInvalid('请选择页面上正序排列的一段连续歌词')
    beats = {word.beat for word in words[start:stop]}
    if len(beats) != 1:
        raise ResegmentInvalid('重分词只能选取同一拍上的连续歌词')


def validate_draft(draft: str, words: tuple[Occurrence, ...], start: int, stop: int) -> list[str]:
    new_words = draft.split()
    if not new_words:
        raise ResegmentInvalid('重分词请至少填一个新词')
    original = ''.join(word.text for word in words[start:stop])
    rewritten = ''.join(new_words)
    # Compare Unicode code points one by one so no char may be added, dropped or rewritten.
    if list(rewritten) != list(original):
        raise ResegmentInvalid('重分词只能重新切分，不得改动拼接后的字')
    return new_words


def apply_resegment(
    words: tuple[Occurrence, ...], start: int, stop: int, draft: list[str], revision: int
) -> tuple[Occurrence, ...]:
    selected = words[start:stop]
    char_keys = tuple(char for word in selected for char in word.chars)
    beat = selected[0].beat
    rewritten = make_resegment_words(revision, draft, beat, char_keys)
    return words[:start] + rewritten + words[stop:]
