import json
from contextlib import closing
from pathlib import Path

from score.web.app import connect_score
from score.web.navigation import preview_url
from tests.support import ScoreCase, record_case


LIANDU_SAMPLE = Path(__file__).resolve().parents[1] / 'samples' / 'liandu.json'


class LianduCase(ScoreCase):
    def setUp(self):
        super().setUp()
        self.source = json.loads(LIANDU_SAMPLE.read_text(encoding='utf-8'))
        self.site.import_source(self.source)

    def page(self, *, browser=None, revision=None, voice='sop', bar='1'):
        from score.web.navigation import worksheet_url
        if revision is None:
            path = worksheet_url(score='liandu', voice=voice, bar=bar)
        else:
            path = worksheet_url(revision=revision, voice=voice, bar=bar)
        status, doc = (browser or self.browser).get(path)
        self.assertEqual(status, 200, ''.join(doc.content))
        return doc

    def submit(self, page, kind, *indexes, fields=None, browser=None):
        form = page.forms[f'{kind}-form']
        data = dict(form.hidden)
        if kind in ('replace', 'resegment'):
            first, last = indexes if len(indexes) == 2 else (indexes[0], indexes[0])
            data['first'] = form.choices['first'][first]
            data['last'] = form.choices['last'][last]
            data['draft'] = (fields or {}).get('draft', '')
        elif kind == 'insert':
            data['gap'] = form.choices['gap'][indexes[0]]
            data['draft'] = (fields or {}).get('draft', '')
        elif kind == 'liaison':
            data['gap'] = form.choices['gap'][indexes[0]]
        return (browser or self.browser).post(form.action, data)

    def preview(self, revision, first='1', last='2', *, browser=None):
        status, doc = (browser or self.browser).get(preview_url(revision, first, last))
        self.assertEqual(status, 200)
        return doc

    def states(self, page):
        return page.mark_states

    def publish(self, page):
        form = page.forms['publish-form']
        return self.browser.post(form.action, form.hidden)


class ResegmentTest(LianduCase):
    def test_merge_and_split_keep_char_identity_and_beat(self):
        page = self.page()
        self.assertEqual(page.word_beats, [0, 0, 0, 0, 2])
        initial_revision = self.site.work('liandu').number
        status, merged = self.submit(page, 'resegment', 0, 1, fields={'draft': '晨光'})
        self.assertEqual(status, 200)
        self.assertEqual(merged.words, ['晨光', '晨', '光', '照'])
        with closing(connect_score(self.site.db)) as db:
            body = db.execute(
                "SELECT body FROM revisions WHERE score='liandu' ORDER BY number DESC LIMIT 1"
            ).fetchone()[0]
        # The merged word reuses the two original char keys, no new identity was minted.
        compact = body.replace(' ', '')
        needle = f'"晨光",0,["{initial_revision}:0.0","{initial_revision}:1.0"]'
        self.assertIn(needle, compact)

        status, split = self.submit(merged, 'resegment', 0, 0, fields={'draft': '晨 光'})
        self.assertEqual(status, 200)
        self.assertEqual(split.words, page.words)
        self.assertEqual(split.word_beats, page.word_beats)
        record_case(
            'ld.resegment', {'draft': ['晨光', '晨 光']},
            page.word_beats, split.word_beats, page.words, split.words,
            ['score/edit/resegment.py', 'score/edit/occurrences.py'],
            'Resegmenting only rewrites word boundaries; char code points, identities and beats stay.',
        )

    def test_single_word_resegment(self):
        page = self.page()
        status, saved = self.submit(page, 'resegment', 0, 0, fields={'draft': '晨'})
        self.assertEqual(status, 200)
        self.assertEqual(saved.words, page.words)

    def test_cross_beat_span_is_invalid(self):
        page = self.page()
        # 光（beat 0）与 照（beat 2）跨拍
        status, rejected = self.submit(page, 'resegment', 3, 4, fields={'draft': '光照'})
        self.assertEqual(status, 400)
        before = self.site.scalar('SELECT count(*) FROM revisions WHERE score = ?', ('liandu',))
        self.assertEqual(before, 1)

    def test_changed_code_points_are_invalid(self):
        page = self.page()
        for draft in ('辰', '晨 晨光', '晨 光x'):
            with self.subTest(draft=draft):
                status, rejected = self.submit(page, 'resegment', 0, 1, fields={'draft': draft})
                self.assertEqual(status, 400)
        self.assertEqual(self.formal_words('liandu'), ['晨', '光', '晨', '光', '照'])

    def test_stale_resegment_conflicts(self):
        page = self.page()
        status, newer = self.submit(page, 'insert', 4, fields={'draft': '停'})
        self.assertEqual(status, 200)
        status, conflict = self.submit(page, 'resegment', 0, 1, fields={'draft': '晨光'})
        self.assertEqual(status, 409)
        self.assertIn('resegment-conflict', conflict.nodes)
        self.assertEqual(conflict.revision, newer.revision)
        self.assertEqual(self.site.scalar('SELECT count(*) FROM revisions WHERE score = ?', ('liandu',)), 2)

    def test_resegment_write_failure_leaves_no_partial_result(self):
        page = self.page()
        before = self.site.scalar('SELECT count(*) FROM revisions WHERE score = ?', ('liandu',))
        with closing(connect_score(self.site.db)) as db, db:
            db.execute('''
                CREATE TRIGGER reject_resegment BEFORE INSERT ON revisions
                BEGIN SELECT RAISE(ABORT, 'rejected'); END
            ''')
        status, response = self.submit(page, 'resegment', 0, 1, fields={'draft': '晨光'})
        self.assertEqual(status, 503)
        with closing(connect_score(self.site.db)) as db, db:
            db.execute('DROP TRIGGER reject_resegment')
        self.assertEqual(
            self.site.scalar('SELECT count(*) FROM revisions WHERE score = ?', ('liandu',)), before
        )
        self.assertEqual(self.formal_words('liandu'), ['晨', '光', '晨', '光', '照'])


class LiaisonWorkflowTest(LianduCase):
    def test_old_page_mark_after_merge_is_hidden_then_visible_after_split(self):
        original = self.page()
        # 乙先把前两词重分为「晨光」
        status, merged = self.submit(original, 'resegment', 0, 1, fields={'draft': '晨光'})
        self.assertEqual(status, 200)
        # 甲凭旧页（修订 1）办理第一、第二词之间的连读
        status, marked = self.submit(original, 'liaison', 0)
        self.assertEqual(status, 200)
        self.assertIn('saved-preview', marked.nodes)
        merged_rev = marked.revision
        preview = self.preview(merged_rev)
        self.assertEqual(self.states(preview), [(1, 'hidden')])
        # 暂隐时排练格不出现连读符号
        self.assertNotIn(('grid', ('sop', '1', 0)), preview.liaisons)

        status, split = self.submit(marked, 'resegment', 0, 0, fields={'draft': '晨 光'})
        self.assertEqual(status, 200)
        self.assertEqual(split.words, ['晨', '光', '晨', '光', '照'])
        # 工作页仅在第一、第二词的实际词缝显示连读
        self.assertEqual(split.liaisons, [('measure', 1)])
        current_rev = split.revision
        visible = self.preview(current_rev)
        self.assertEqual(self.states(visible), [(1, 'visible')])
        self.assertIn(('grid', ('sop', '1', 0)), visible.liaisons)
        # 较早版本仍按办理当时的状态预览
        older = self.preview(merged_rev)
        self.assertEqual(self.states(older), [(1, 'hidden')])
        # 第三、第四词同样是「晨 光」，但没有该标记
        self.assertEqual(
            [cell for kind, cell in visible.liaisons if kind == 'grid' and cell[0] == 'sop'],
            [('sop', '1', 0)],
        )
        record_case(
            'ld.hide_show', {'merge': '晨光', 'split': '晨 光'},
            [('1', 'hidden')], self.states(older),
            [('1', 'visible')], self.states(visible),
            ['score/liandu/state.py', 'score/rehearse/preview.py'],
            'The same original seam hides inside one word and reappears at the restored boundary.',
        )

    def test_inserted_word_hides_and_removal_restores(self):
        original = self.page()
        status, marked_page = self.submit(original, 'liaison', 0)
        self.assertEqual(status, 200)
        old_gap = original.forms['liaison-form'].choices['gap'][0]
        status, inserted = self.submit(marked_page, 'insert', 1, fields={'draft': '且'})
        self.assertEqual(status, 200)
        self.assertEqual(inserted.words, ['晨', '且', '光', '晨', '光', '照'])
        hidden = self.preview(inserted.revision, '1', '1')
        self.assertEqual(self.states(hidden), [(1, 'hidden')])
        # 被隔开时，未办理的原缝表单报冲突
        status, conflict = self.browser.post('/edit', {
            'kind': 'liaison', 'voice': 'sop', 'bar': '1', 'gap': old_gap,
        })
        self.assertEqual(status, 409)
        self.assertIn('liaison-conflict', conflict.nodes)
        # 普通空替换删除插入词后复显
        target = inserted.forms['replace-form'].choices['first'][1]
        status, restored = self.browser.post('/edit', {
            'kind': 'replace', 'voice': 'sop', 'bar': '1',
            'first': target, 'last': target, 'draft': '',
        })
        self.assertEqual(status, 200)
        self.assertEqual(restored.words, ['晨', '光', '晨', '光', '照'])
        self.assertEqual(restored.liaisons, [('measure', 1)])

    def test_same_text_rewrite_kills_mark_forever(self):
        original = self.page()
        status, marked_page = self.submit(original, 'liaison', 0)
        self.assertEqual(status, 200)
        old_gap = original.forms['liaison-form'].choices['gap'][0]
        target = marked_page.forms['replace-form'].choices['first'][0]
        status, rewritten = self.browser.post('/edit', {
            'kind': 'replace', 'voice': 'sop', 'bar': '1',
            'first': target, 'last': target, 'draft': '晨',
        })
        self.assertEqual(status, 200)
        # 词文与拍位照旧，但左字取得了新身份，标记永久失效
        self.assertEqual(rewritten.words, ['晨', '光', '晨', '光', '照'])
        dead = self.preview(rewritten.revision, '1', '1')
        self.assertEqual(self.states(dead), [(1, 'dead')])
        self.assertEqual(dead.liaisons, [])
        status, conflict = self.browser.post('/edit', {
            'kind': 'liaison', 'voice': 'sop', 'bar': '1', 'gap': old_gap,
        })
        self.assertEqual(status, 409)

    def test_visible_mark_only_belongs_to_its_own_seam_and_voice(self):
        page = self.page()
        # 高声部第一缝
        status, sop_mark = self.submit(page, 'liaison', 0)
        self.assertEqual(status, 200)
        # 低声部小节 1 同样是「晨 光」，独立办理
        alto = self.page(voice='alto')
        self.assertEqual(len(alto.forms['liaison-form'].choices['gap']), 1)
        status, alto_mark = self.submit(alto, 'liaison', 0)
        self.assertEqual(status, 200)
        preview = self.preview(sop_mark.revision)
        grid_marks = [cell for kind, cell in preview.liaisons if kind == 'grid']
        self.assertEqual(sorted(grid_marks), [('alto', '1', 0), ('sop', '1', 0)])

    def test_repeated_liaison_on_same_seam_is_idempotent(self):
        page = self.page()
        status, first = self.submit(page, 'liaison', 0)
        self.assertEqual(status, 200)
        status, second = self.submit(page, 'liaison', 0)
        self.assertEqual(status, 200)
        self.assertEqual(self.site.scalar('SELECT count(*) FROM liaisons'), 1)
        preview = self.preview(first.revision, '1', '1')
        self.assertEqual(
            [cell for kind, cell in preview.liaisons if kind == 'grid'],
            [('sop', '1', 0)],
        )

    def test_liaison_form_validity(self):
        # 空小节没有连读表单
        status, doc = self.browser.get('/worksheet?score=liandu&voice=alto&bar=2')
        self.assertEqual(status, 200)
        self.assertNotIn('liaison-form', doc.forms)
        # 非法表单
        status, rejected = self.browser.post('/edit', {
            'kind': 'liaison', 'voice': 'sop', 'bar': '1', 'gap': 'not-json',
        })
        self.assertEqual(status, 400)
        # 未知工作版
        status, missing = self.browser.post('/edit', {
            'kind': 'liaison', 'voice': 'sop', 'bar': '1', 'gap': json.dumps([999, '1:0', '1:1']),
        })
        self.assertEqual(status, 404)
        # 未知声部小节
        page = self.page()
        gap = page.forms['liaison-form'].choices['gap'][0]
        status, missing_line = self.browser.post('/edit', {
            'kind': 'liaison', 'voice': 'sop', 'bar': '9', 'gap': gap,
        })
        self.assertEqual(status, 404)

    def test_liaison_write_failure_is_atomic(self):
        page = self.page()
        with closing(connect_score(self.site.db)) as db, db:
            db.execute('''
                CREATE TRIGGER reject_liaison BEFORE INSERT ON liaisons
                BEGIN SELECT RAISE(ABORT, 'rejected'); END
            ''')
        status, response = self.submit(page, 'liaison', 0)
        self.assertEqual(status, 503)
        with closing(connect_score(self.site.db)) as db, db:
            db.execute('DROP TRIGGER reject_liaison')
        self.assertEqual(self.site.scalar('SELECT count(*) FROM liaisons'), 0)
        current = self.site.scalar('SELECT revision FROM current_revisions WHERE score = ?', ('liandu',))
        self.assertEqual(
            self.site.scalar('SELECT revision FROM current_revisions WHERE score = ?', ('liandu',)),
            current,
        )


class EditionLiaisonTest(LianduCase):
    def test_edition_freezes_visible_marks_and_reopens(self):
        original = self.page()
        status, marked = self.submit(original, 'liaison', 0)
        self.assertEqual(status, 200)
        revision = marked.revision
        preview = self.preview(revision)
        status, edition = self.publish(preview)
        self.assertEqual(status, 201)
        # 拍格、换气、连读一并固定
        self.assertEqual(edition.cells, preview.cells)
        self.assertEqual(
            [cell for kind, cell in edition.liaisons if kind == 'grid'],
            [cell for kind, cell in preview.liaisons if kind == 'grid'],
        )
        number = edition.nodes['edition']['data-number']
        # 签存后再改稿，原定稿不变
        target = marked.forms['replace-form'].choices['first'][0]
        status, rewritten = self.browser.post('/edit', {
            'kind': 'replace', 'voice': 'sop', 'bar': '1',
            'first': target, 'last': target, 'draft': '晨',
        })
        self.assertEqual(status, 200)
        self.site.restart()
        browser = self.site.browser()
        status, reopened = browser.get(edition.nodes['edition-link']['href'])
        self.assertEqual(status, 200)
        self.assertEqual(reopened.cells, edition.cells)
        self.assertEqual(reopened.liaisons, edition.liaisons)
        self.assertEqual(reopened.nodes['edition']['data-number'], number)
        record_case(
            'ld.edition', {'signed_revision': revision},
            [('sop', '1', 0)], [c for k, c in edition.liaisons if k == 'grid'],
            [('sop', '1', 0)], [c for k, c in reopened.liaisons if k == 'grid'],
            ['score/edition/snapshot.py', 'score/edition/readback.py'],
            'The signed edition keeps the visible liaison at its seam after edits and a service restart.',
        )

    def test_hidden_marks_are_not_written_into_edition(self):
        original = self.page()
        status, merged = self.submit(original, 'resegment', 0, 1, fields={'draft': '晨光'})
        self.assertEqual(status, 200)
        status, marked = self.submit(original, 'liaison', 0)
        self.assertEqual(status, 200)
        preview = self.preview(marked.revision)
        self.assertEqual(self.states(preview), [(1, 'hidden')])
        status, edition = self.publish(preview)
        self.assertEqual(status, 201)
        self.assertEqual([item for item in edition.liaisons if item[0] == 'grid'], [])
        # 无标记定稿继续可领取
        initial = self.site.work('liandu').number
        plain = self.preview(initial)
        status, plain_edition = self.publish(plain)
        self.assertEqual(status, 201)
        self.assertEqual(plain_edition.liaisons, [])

    def test_edition_write_failure_rolls_back(self):
        original = self.page()
        status, marked = self.submit(original, 'liaison', 0)
        self.assertEqual(status, 200)
        preview = self.preview(marked.revision)
        with closing(connect_score(self.site.db)) as db, db:
            db.execute('''
                CREATE TRIGGER reject_snapshot BEFORE INSERT ON edition_snapshots
                BEGIN SELECT RAISE(ABORT, 'snapshot rejected'); END
            ''')
        status, response = self.publish(preview)
        self.assertEqual(status, 503)
        with closing(connect_score(self.site.db)) as db, db:
            db.execute('DROP TRIGGER reject_snapshot')
        self.assertEqual(self.site.scalar('SELECT count(*) FROM editions'), 0)
        self.assertEqual(self.site.scalar('SELECT count(*) FROM edition_snapshots'), 0)


class OrdinaryEditInteropTest(LianduCase):
    def test_ordinary_rewrites_never_inherit_old_marks(self):
        # 普通替换写入的新字即使同字同拍，也不能承接原标记
        page = self.page()
        status, marked = self.submit(page, 'liaison', 0)
        self.assertEqual(status, 200)
        # 删去「光」再以普通插入写回同字
        target = marked.forms['replace-form'].choices['first'][1]
        status, removed = self.browser.post('/edit', {
            'kind': 'replace', 'voice': 'sop', 'bar': '1',
            'first': target, 'last': target, 'draft': '',
        })
        self.assertEqual(status, 200)
        gap = removed.forms['insert-form'].choices['gap'][1]
        status, reentered = self.browser.post('/edit', {
            'kind': 'insert', 'voice': 'sop', 'bar': '1', 'gap': gap, 'draft': '光',
        })
        self.assertEqual(status, 200)
        self.assertEqual(reentered.words, ['晨', '光', '晨', '光', '照'])
        preview = self.preview(reentered.revision, '1', '1')
        self.assertEqual(self.states(preview), [(1, 'dead')])

    def test_resegment_does_not_disturb_unrelated_edits(self):
        # 普通编辑与重分词产生的修订正文都能读出字符键
        page = self.page()
        status, replaced = self.submit(page, 'replace', 4, 4, fields={'draft': '耀'})
        self.assertEqual(status, 200)
        status, segmented = self.submit(replaced, 'resegment', 0, 1, fields={'draft': '晨光'})
        self.assertEqual(status, 200)
        self.assertEqual(segmented.words, ['晨光', '晨', '光', '耀'])
        self.assertEqual(segmented.word_beats, [0, 0, 0, 2])
