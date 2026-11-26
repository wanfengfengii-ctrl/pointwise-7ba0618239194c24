from score.web.navigation import preview_url
from tests.support import ScoreCase, record_case


class PracticeTest(ScoreCase):
    def test_voice_alignment(self):
        status, page = self.browser.get(preview_url(self.site.work().number, '1', '1'))
        self.assertEqual(status, 200)
        self.assertEqual(page.columns, [('1', 0), ('1', 1), ('1', 2), ('1', 3)])
        self.assertEqual(page.voice_order, ['sop', 'alto'])
        expected = {
            ('sop', '1', 0): ('A B', False), ('sop', '1', 1): ('', True),
            ('sop', '1', 2): ('C', False), ('sop', '1', 3): ('', False),
            ('alto', '1', 0): ('', True), ('alto', '1', 1): ('D', False),
            ('alto', '1', 2): ('', False), ('alto', '1', 3): ('', False),
        }
        self.assertEqual(page.cells, expected)
        form = page.forms['publish-form']
        status, edition = self.browser.post(form.action, form.hidden)
        self.assertEqual(status, 201)
        self.assertEqual(edition.cells, expected)
        self.assertEqual(edition.voice_order, ['sop', 'alto'])
        marked = ('sop', '1', 1)
        record_case('v7', {'sop': [[0, 'A'], [0, 'B'], [2, 'C']], 'alto': [[1, 'D']]},
                    ['', True], list(page.cells[marked]), ['', True], list(edition.cells[marked]),
                    ['score/rehearse/beat_grid.py', 'score/rehearse/breath_cues.py', 'score/edition/snapshot.py'],
                    'At beat index 1 the upper voice rests immediately before C. The lower voice sings D in that same column.')

    def test_cue_range(self):
        revision = self.site.work().number
        code, short = self.browser.get(preview_url(revision, '1', '1'))
        self.assertEqual(code, 200)
        code, longer = self.browser.get(preview_url(revision, '1', '2'))
        self.assertEqual(code, 200)
        self.assertEqual(short.cells['sop', '1', 3], ('', False))
        self.assertEqual(longer.cells['sop', '1', 3], ('', True))
        self.assertEqual(longer.cells['sop', '2', 0], ('E', False))
        self.assertEqual(longer.cells['sop', '2', 2], ('', False))
        self.assertEqual([longer.cells['alto', '2', beat] for beat in range(3)], [('', False)] * 3)
        status, complete = self.browser.get(preview_url(revision, '1', '10'))
        self.assertEqual(status, 200)
        self.assertEqual(complete.columns, [('1', 0), ('1', 1), ('1', 2), ('1', 3),
                                            ('2', 0), ('2', 1), ('2', 2), ('10', 0), ('10', 1)])

    def test_invalid_range(self):
        revision = self.site.work().number
        for first, last in [('missing', '2'), ('1', 'missing'), ('10', '2')]:
            with self.subTest(first=first, last=last):
                status, page = self.browser.get(preview_url(revision, first, last))
                self.assertEqual(status, 400)
                self.assertNotIn('practice-grid', page.nodes)
        status, _ = self.browser.get(preview_url(999, '1', '2'))
        self.assertEqual(status, 404)
