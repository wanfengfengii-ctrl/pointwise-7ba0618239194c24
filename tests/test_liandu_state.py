import unittest

from score.edit.occurrences import Occurrence
from score.liandu.state import DEAD, HIDDEN, VISIBLE, chars_adjacent, evaluate_mark
from score.liandu.store import LiaisonMark


def make_words(*specs) -> tuple[Occurrence, ...]:
    words = []
    for key, text, beat in specs:
        chars = tuple(f'{key}.{index}' for index in range(len(text)))
        words.append(Occurrence(key, text, beat, chars))
    return tuple(words)


def mark(left: str, right: str) -> LiaisonMark:
    return LiaisonMark(1, 'liandu', 1, 'sop', '1', left, right)


class LiaisonStateTest(unittest.TestCase):
    def test_word_boundary_is_visible(self):
        words = make_words(('a', '晨L', 0), ('b', 'R光', 0))
        self.assertEqual(evaluate_mark(mark('a.1', 'b.0'), words).state, VISIBLE)

    def test_adjacent_inside_one_word_is_hidden(self):
        words = make_words(('a', 'LR', 0), ('b', '光', 0))
        self.assertEqual(evaluate_mark(mark('a.0', 'a.1'), words).state, HIDDEN)

    def test_inserted_word_between_is_hidden(self):
        words = make_words(('a', 'L', 0), ('x', '且', 0), ('b', 'R', 0))
        self.assertEqual(evaluate_mark(mark('a.0', 'b.0'), words).state, HIDDEN)

    def test_replaced_char_is_dead_forever(self):
        words = make_words(('z', 'L', 0), ('b', 'R', 0))
        self.assertEqual(evaluate_mark(mark('a.0', 'b.0'), words).state, DEAD)
        # 后续版本即使出现同位置新字，原键缺失依旧失效
        later = make_words(('z', 'L', 0), ('b', 'R', 0), ('c', '尾', 0))
        self.assertEqual(evaluate_mark(mark('a.0', 'b.0'), later).state, DEAD)

    def test_reversed_order_is_not_adjacent(self):
        words = make_words(('b', 'R', 0), ('a', 'L', 0))
        self.assertEqual(evaluate_mark(mark('a.0', 'b.0'), words).state, HIDDEN)

    def test_adjacency_helper(self):
        words = make_words(('a', 'LR', 0), ('b', '光', 0))
        from score.liandu.state import index_chars
        records = index_chars(words)
        self.assertTrue(chars_adjacent(records['a.0'], records['a.1']))
        self.assertTrue(chars_adjacent(records['a.1'], records['b.0']))
        self.assertFalse(chars_adjacent(records['a.0'], records['b.0']))


if __name__ == '__main__':
    unittest.main()
