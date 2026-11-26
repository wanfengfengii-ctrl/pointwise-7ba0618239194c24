import threading
from concurrent.futures import ThreadPoolExecutor

from tests.support import ScoreCase, choice, record_case, sample_source


class EditingTest(ScoreCase):
    def test_replace_from_current_page(self):
        page = self.worksheet()
        status, saved = self.submit(page, 'replace', 1, 2, draft='X')
        self.assertEqual(status, 200)
        self.assertEqual(saved.words, ['A', 'X'])
        self.assertEqual(saved.word_beats, [0, 0])
        self.assertEqual(self.formal_words(), saved.words)
        self.assertEqual(self.site.scalar('SELECT count(*) FROM revisions'), 2)
        old = self.site.work(revision=page.revision).line('sop', '1')
        new = self.site.work().line('sop', '1')
        self.assertEqual(old[0].key, new[0].key)
        self.assertNotIn(new[1].key, {word.key for word in old})

    def test_empty_bar_gap(self):
        page = self.worksheet(bar='10')
        self.assertEqual(page.words, [])
        self.assertNotIn('replace-form', page.forms)
        self.assertEqual(len(page.forms['insert-form'].choices['gap']), 1)
        rejected, _ = self.submit(page, 'insert', 0, draft='  ')
        self.assertEqual(rejected, 400)
        self.assertEqual(self.site.scalar('SELECT count(*) FROM revisions'), 1)
        status, saved = self.submit(page, 'insert', 0, draft='明 早')
        self.assertEqual(status, 200)
        self.assertEqual(saved.words, ['明', '早'])
        self.assertEqual(saved.word_beats, [0, 0])
        self.assertEqual(self.formal_words(bar='10'), ['明', '早'])

    def _inside_insert(self, draft='X'):
        beta = self.site.browser()
        a = self.worksheet()
        b = self.worksheet(browser=beta)
        self.assertEqual(a.revision, b.revision)
        stale = choice(a, 'replace', 1, 2, draft=draft)
        status, written = self.submit(b, 'insert', 2, draft='Y', browser=beta)
        self.assertEqual(status, 200)
        self.assertEqual(written.words, ['A', 'B', 'Y', 'C'])
        counts_before = self.site.scalar('SELECT count(*) FROM revisions')
        status, conflict = self.browser.post(*stale)
        self.assertEqual(status, 409, 'INSIDE_INSERT_CONFLICT: stale replacement must be rejected')
        self.assertEqual(conflict.forms['replace-form'].draft, draft)
        self.assertEqual(conflict.revision, written.revision)
        self.assertEqual(conflict.words, ['A', 'B', 'Y', 'C'])
        mark = conflict.nodes['edit-conflict']
        self.assertEqual((mark['data-start'], mark['data-stop']), ('2', '3'))
        self.assertIn('当前第 3 至 3 词：Y', ''.join(conflict.content))
        self.assertEqual(self.formal_words(), ['A', 'B', 'Y', 'C'])
        self.assertEqual(self.site.scalar('SELECT count(*) FROM revisions'), counts_before)
        return conflict, status

    def test_internal_insert_conflicts(self):
        conflict, status = self._inside_insert()
        record_case('v4', {'initial': ['A', 'B', 'C'], 'edits': ['B | C → Y', 'B C → X']},
                    {'status': 409, 'draft': 'X'},
                    {'status': status, 'draft': conflict.forms['replace-form'].draft},
                    ['A', 'B', 'Y', 'C'], self.formal_words(),
                    ['score/web/edit_form.py', 'score/edit/commit.py', 'score/web/edit_result.py'],
                    'Y interrupts the original adjacency. Only the first edit can enter the formal score.')

    def test_retry_selection(self):
        conflict, _ = self._inside_insert()
        status, retried = self.submit(conflict, 'replace', 1, draft=conflict.forms['replace-form'].draft)
        self.assertEqual(status, 200)
        self.assertEqual(retried.words, ['A', 'X', 'Y', 'C'])
        self.assertEqual(self.formal_words(), retried.words)
        self.assertEqual(self.site.scalar('SELECT count(*) FROM revisions'), 3)

    def test_same_gap_order(self):
        alpha, beta = self.site.browser(), self.site.browser()
        alpha_page = self.worksheet(browser=alpha)
        beta_page = self.worksheet(browser=beta)
        self.assertEqual(alpha_page.revision, beta_page.revision)
        submissions = [choice(alpha_page, 'insert', 2, draft='Y'), choice(beta_page, 'insert', 2, draft='Z')]
        barrier = threading.Barrier(2)

        def submit_at_barrier(browser, submission):
            barrier.wait(timeout=10)
            return browser.post(*submission)

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(submit_at_barrier, alpha, submissions[0])
            second = pool.submit(submit_at_barrier, beta, submissions[1])
            responses = [first.result(timeout=20), second.result(timeout=20)]
        self.assertCountEqual([status for status, _ in responses], [200, 409])
        winner, conflict = sorted(responses, key=lambda pair: pair[0])
        words = self.formal_words()
        winning_word = 'Y' if responses[0][0] == 200 else 'Z'
        losing_word = 'Z' if winning_word == 'Y' else 'Y'
        self.assertEqual(words, ['A', 'B', winning_word, 'C'])
        self.assertEqual(conflict[1].forms['insert-form'].draft, losing_word)
        for _, page in (winner, conflict):
            self.assertEqual(page.words, words)
            self.assertEqual(page.revision, self.site.work().number)
        self.assertEqual(self.site.scalar('SELECT count(*) FROM revisions'), 2)

    def test_outside_insert_merges(self):
        alpha, beta = self.site.browser(), self.site.browser()
        a, b = self.worksheet(browser=alpha), self.worksheet(browser=beta)
        self.assertEqual(a.revision, b.revision)
        stale = choice(a, 'replace', 1, 2, draft='X')
        status, added = beta.post(*choice(b, 'insert', 3, draft='Y'))
        self.assertEqual(status, 200)
        self.assertEqual(added.words, ['A', 'B', 'C', 'Y'])
        status, saved = alpha.post(*stale)
        self.assertEqual(status, 200)
        self.assertEqual(saved.words, ['A', 'X', 'Y'])
        self.assertEqual(self.formal_words(), saved.words)
        preview_status, preview = alpha.get(saved.nodes['saved-preview']['href'])
        self.assertEqual(preview_status, 200)
        self.assertEqual(preview.revision, saved.revision)
        self.assertEqual(preview.lyrics('sop', '1'), ['A', 'X', 'Y'])
        self.assertEqual(preview.cells['sop', '1', 2], ('Y', False))
        self.assertEqual(self.site.scalar('SELECT count(*) FROM revisions'), 3)
        record_case('v5.form_roundtrip', {'initial': ['A', 'B', 'C'], 'edits': ['C | end → Y', 'B C → X']},
                    ['A', 'X', 'Y'], saved.words, ['A', 'X', 'Y'], preview.lyrics('sop', '1'),
                    ['score/web/edit_form.py', 'score/edit/commit.py', 'score/rehearse/preview.py'],
                    'X replaces the adjacent original B and C. Y is outside that span and stays on the former C beat.')

    def test_same_text_new_occurrence(self):
        old = self.worksheet()
        original = self.site.work().line('sop', '1')[1]
        status, removed = self.submit(old, 'replace', 1, draft='')
        self.assertEqual(status, 200)
        self.assertEqual(removed.words, ['A', 'C'])
        status, reentered = self.submit(removed, 'insert', 1, draft='B')
        self.assertEqual(status, 200)
        self.assertEqual(reentered.words, ['A', 'B', 'C'])
        self.assertNotEqual(original.key, self.site.work().line('sop', '1')[1].key)
        status, conflict = self.submit(old, 'replace', 1, draft='X')
        self.assertEqual(status, 409)
        self.assertEqual(conflict.forms['replace-form'].draft, 'X')
        self.assertEqual(conflict.words, reentered.words)
        self.assertEqual(self.site.work().number, reentered.revision)
        self.assertEqual(self.site.scalar('SELECT count(*) FROM revisions'), 3)

    def test_identical_visible_history(self):
        histories = []
        outcomes = []
        for score, removed_index, insertion_index in (('kept', 2, 2), ('reentered', 1, 1)):
            alpha, beta = self.site.browser(), self.site.browser()
            source = sample_source()
            source['score'] = score
            lyrics = source['voices'][0]['lyrics']
            lyrics.insert(2, dict(lyrics[1]))
            self.site.import_source(source)
            old_a = self.worksheet(browser=alpha, score=score)
            old_b = self.worksheet(browser=beta, score=score)
            original_key = self.site.work(score).line('sop', '1')[1].key
            status, reduced = self.submit(old_b, 'replace', removed_index, draft='', browser=beta)
            self.assertEqual(status, 200)
            status, expanded = self.submit(reduced, 'insert', insertion_index, draft='B', browser=beta)
            self.assertEqual(status, 200)
            histories.append([list(zip(p.words, p.word_beats)) for p in (old_a, reduced, expanded)])
            now_key = self.site.work(score).line('sop', '1')[1].key
            self.assertEqual(now_key == original_key, score == 'kept')
            status, page = self.submit(old_a, 'replace', 1, draft='X', browser=alpha)
            outcomes.append((status, page.words, self.site.scalar('SELECT count(*) FROM revisions WHERE score = ?', (score,))))
            self.assertEqual(page.words, self.formal_words(score))
            if score == 'reentered':
                self.assertEqual(page.forms['replace-form'].draft, 'X')
                self.assertIn('edit-conflict', page.nodes)
        expected_history = [
            [('A', 0), ('B', 0), ('B', 0), ('C', 2)],
            [('A', 0), ('B', 0), ('C', 2)],
            [('A', 0), ('B', 0), ('B', 0), ('C', 2)],
        ]
        self.assertEqual(histories, [expected_history, expected_history])
        self.assertEqual(outcomes, [(200, ['A', 'X', 'B', 'C'], 4), (409, ['A', 'B', 'B', 'C'], 3)])

    def test_shifted_range_and_boundaries(self):
        old = self.worksheet()
        status, shifted = self.submit(old, 'insert', 0, draft='Lead')
        self.assertEqual(status, 200)
        self.assertEqual(shifted.words, ['Lead', 'A', 'B', 'C'])
        status, saved = self.submit(old, 'replace', 1, 2, draft='X')
        self.assertEqual((status, saved.words), (200, ['Lead', 'A', 'X']))
        status, conflict = self.submit(old, 'insert', 0, draft='Again')
        self.assertEqual(status, 409)
        self.assertEqual(conflict.forms['insert-form'].draft, 'Again')

    def test_draft_and_words_are_text(self):
        draft = '\n<script>&词</script>'
        conflict, _ = self._inside_insert(draft)
        self.assertEqual(conflict.forms['replace-form'].draft, draft)
        status, saved = self.submit(conflict, 'replace', 1, draft=draft)
        self.assertEqual(status, 200)
        self.assertEqual(saved.words, ['A', '<script>&词</script>', 'Y', 'C'])

    def test_missing_worksheet_and_inverted_selection(self):
        status, _ = self.browser.get('/worksheet?revision=999&voice=sop&bar=1')
        self.assertEqual(status, 404)
        status, _ = self.browser.get('/worksheet?score=wangxi&voice=sop&bar=missing')
        self.assertEqual(status, 404)
        status, _ = self.submit(self.worksheet(), 'replace', 2, 1, draft='X')
        self.assertEqual(status, 400)
        self.assertEqual(self.site.scalar('SELECT count(*) FROM revisions'), 1)
