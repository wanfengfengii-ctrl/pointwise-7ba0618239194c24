from contextlib import closing

from score.web.app import connect_score
from score.web.navigation import edition_url, preview_url
from tests.support import ScoreCase, record_case


class EditionTest(ScoreCase):
    def _publish_preview(self, revision, first='1', last='1'):
        status, preview = self.browser.get(preview_url(revision, first, last))
        self.assertEqual(status, 200)
        form = preview.forms['publish-form']
        status, edition = self.browser.post(form.action, form.hidden)
        self.assertEqual(status, 201)
        self.assertEqual(edition.cells, preview.cells)
        self.assertEqual(edition.columns, preview.columns)
        self.assertEqual(edition.voice_order, preview.voice_order)
        return preview, edition

    def test_read_after_new_edit(self):
        old = self.worksheet()
        preview, signed = self._publish_preview(old.revision, '1', '2')
        status, edited = self.submit(old, 'replace', 1, 2, draft='新版')
        self.assertEqual(status, 200)
        old_address = signed.nodes['edition-link']['href']
        self.site.restart()
        reopened_browser = self.site.browser()
        status, archived = reopened_browser.get(old_address)
        self.assertEqual(status, 200)
        self.assertEqual(archived.revision, old.revision)
        self.assertEqual(archived.cells, preview.cells)
        self.assertEqual(archived.columns, preview.columns)
        self.assertEqual(archived.voice_order, ['sop', 'alto'])
        self.assertEqual(archived.lyrics('sop', '1'), ['A', 'B', 'C'])
        current = self.worksheet(browser=reopened_browser)
        self.assertEqual(current.revision, edited.revision)
        self.assertEqual(current.words, ['A', '新版'])
        self.assertEqual(self.worksheet(browser=reopened_browser, revision=old.revision).words, ['A', 'B', 'C'])
        record_case('v8', {'signed_revision': old.revision, 'later_edit': 'B C → 新版'},
                    ['A', '新版'], current.words, ['A', 'B', 'C'], archived.lyrics('sop', '1'),
                    ['score/edit/revisions.py', 'score/edition/snapshot.py', 'score/edition/readback.py'],
                    'A subsequent edit advances the workbench. The already printed rehearsal words and cues still come from the signed revision.')

    def test_selected_revision(self):
        old = self.worksheet()
        status, newer = self.submit(old, 'insert', 3, draft='Y')
        self.assertEqual(status, 200)
        preview, old_edition = self._publish_preview(old.revision, '1', '2')
        self.assertEqual(old_edition.revision, old.revision)
        self.assertEqual(preview.lyrics('sop', '1'), ['A', 'B', 'C'])
        self.assertEqual(old_edition.cells['sop', '1', 3], ('', True))
        self.assertEqual(old_edition.columns, [('1', 0), ('1', 1), ('1', 2), ('1', 3), ('2', 0), ('2', 1), ('2', 2)])
        _, new_edition = self._publish_preview(newer.revision)
        self.assertNotEqual(old_edition.nodes['edition']['data-number'], new_edition.nodes['edition']['data-number'])
        self.assertEqual(new_edition.lyrics('sop', '1'), ['A', 'B', 'C', 'Y'])
        self.assertEqual(self.site.scalar('SELECT count(*) FROM editions'), 2)

    def test_unknown_edition(self):
        status, page = self.browser.get(edition_url(111))
        self.assertEqual(status, 404)
        self.assertNotIn('practice-grid', page.nodes)

    def test_missing_revision_has_no_edition(self):
        before = self.site.scalar('SELECT count(*) FROM editions')
        status, response = self.browser.post('/edition', {'revision': '999', 'first': '1', 'last': '2'})
        self.assertEqual(status, 404)
        self.assertNotIn('edition', response.nodes)
        self.assertEqual(self.site.scalar('SELECT count(*) FROM editions'), before)
        self.assertEqual(self.site.scalar('SELECT count(*) FROM edition_snapshots'), 0)
        status, _ = self.browser.post('/edition', {'revision': str(self.site.work().number), 'first': '2', 'last': '1'})
        self.assertEqual(status, 400)
        self.assertEqual(self.site.scalar('SELECT count(*) FROM editions'), before)

    def test_sign_failure(self):
        _, baseline = self._publish_preview(self.site.work().number)
        status, preview = self.browser.get(preview_url(self.site.work().number, '1', '2'))
        self.assertEqual(status, 200)
        form = preview.forms['publish-form']
        with closing(connect_score(self.site.db)) as db, db:
            db.execute('''
                CREATE TRIGGER reject_snapshot BEFORE INSERT ON edition_snapshots
                BEGIN SELECT RAISE(ABORT, 'snapshot write rejected'); END
            ''')
        status, response = self.browser.post(form.action, form.hidden)
        self.assertEqual(status, 503)
        self.assertIn('定稿写入失败', ''.join(response.content))
        self.assertNotIn('edition', response.nodes)
        self.assertEqual(self.site.scalar('SELECT count(*) FROM editions'), 1)
        self.assertEqual(self.site.scalar('SELECT count(*) FROM edition_snapshots'), 1)
        self.site.restart()
        self.browser = self.site.browser()
        expected_next = int(baseline.nodes['edition']['data-number']) + 1
        status, _ = self.browser.get(edition_url(expected_next))
        self.assertEqual(status, 404)
        status, previous_edition = self.browser.get(baseline.nodes['edition-link']['href'])
        self.assertEqual(status, 200)
        self.assertEqual(previous_edition.cells, baseline.cells)
        with closing(connect_score(self.site.db)) as db, db:
            db.execute('DROP TRIGGER reject_snapshot')
        _, recovered = self._publish_preview(self.site.work().number, '1', '2')
        self.assertEqual(int(recovered.nodes['edition']['data-number']), expected_next)
        self.assertEqual(self.site.scalar('SELECT count(*) FROM editions'), 2)
        self.assertEqual(self.site.scalar('SELECT count(*) FROM edition_snapshots'), 2)
