import json

from tests.support import ScoreCase, record_case, sample_source


class ImportTest(ScoreCase):
    def test_initialize_preserves_edit(self):
        page = self.worksheet()
        status, edited = self.submit(page, 'replace', 0, draft='新唱词')
        self.assertEqual(status, 200)
        self.assertGreater(edited.revision, page.revision)
        response = self.site.command('init')
        self.assertEqual(json.loads(response.stdout), {'score': 'wangxi', 'revision': edited.revision})
        self.site.restart()
        fresh = self.worksheet(browser=self.site.browser())
        self.assertEqual(fresh.words, ['新唱词', 'B', 'C'])
        self.assertEqual(fresh.revision, edited.revision)
        self.assertEqual(self.site.scalar('SELECT count(*) FROM sources'), 1)
        self.assertEqual(self.site.scalar('SELECT count(*) FROM revisions'), 2)
        self.assertEqual(self.worksheet(browser=self.site.browser(), revision=page.revision).words, ['A', 'B', 'C'])

    def test_reject_out_of_bar(self):
        before = self.site.work().number
        source = sample_source()
        source['score'] = 'boundary'
        source['voices'][0]['lyrics'][0]['beat'] = 4
        failed = self.site.import_source(source, check=False)
        self.assertEqual(failed.returncode, 2)
        self.assertIn('拍位 4 超出小节', failed.stderr)
        source_count = self.site.scalar('SELECT count(*) FROM sources')
        version_count = self.site.scalar('SELECT count(*) FROM revisions')
        self.assertEqual((source_count, version_count), (1, 1))
        self.assertEqual(self.site.work().number, before)
        original = self.worksheet()
        self.assertEqual(original.words, ['A', 'B', 'C'])
        record_case('v2', {'bar_beats': 4, 'word_beat': 4}, {'sources': 1, 'versions': 1},
                    {'sources': source_count, 'versions': version_count}, ['A', 'B', 'C'], original.words,
                    ['score/source/meter.py', 'score/source/import_score.py', 'score/web/worksheet.py'],
                    'A four-beat bar contains only positions 0, 1, 2 and 3. A rejected import leaves the example untouched.')
        source['voices'][0]['lyrics'][0]['beat'] = 3
        accepted = self.site.import_source(source)
        self.assertEqual(json.loads(accepted.stdout)['score'], 'boundary')
        self.assertEqual(self.worksheet(score='boundary').word_beats, [3, 0, 2])
