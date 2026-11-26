import json
import unittest
from contextlib import closing
from pathlib import Path
from urllib.parse import urlencode

from score.edit.commit import submit_edit
from score.edition.publish import initialize_edition_store, publish_edition
from score.edition.readback import read_edition, render_edition
from score.liandu.store import initialize_liaison_store
from score.rehearse.preview import build_preview, render_preview
from score.source.import_score import import_score, initialize_source_store
from score.web.app import connect_score
from score.web.edit_form import decode_edit_form
from score.web.edit_result import render_edit_result
from score.web.navigation import worksheet_url
from score.web.worksheet import render_worksheet
from tests.support import Page, ScoreCase, choice


SAMPLE = Path(__file__).resolve().parent / "samples" / "liandu.json"


def ordinary_edit(db, page, kind, first, last=None, *, draft):
    _, fields = choice(page, kind, first, last, draft=draft)
    form = decode_edit_form(urlencode(fields))
    result = submit_edit(db, form.selection, form.draft)
    status, body = render_edit_result(db, result, form.draft)
    return status, Page(body)


class LianduSeedTest(unittest.TestCase):
    def play_ordinary_history(self, source, merge_and_split):
        with closing(connect_score(":memory:")) as db:
            initialize_source_store(db)
            initialize_edition_store(db)
            initialize_liaison_store(db)
            initial = import_score(db, source)
            original = Page(render_worksheet(db, revision=initial.number, voice="sop", bar="1"))
            self.assertEqual(original.words, ["晨", "光", "晨", "光", "照"])
            self.assertEqual(original.word_beats, [0, 0, 0, 0, 2])
            if merge_and_split:
                status, merged = ordinary_edit(db, original, "replace", 0, 1, draft="晨光")
                self.assertEqual((status, merged.words), (200, ["晨光", "晨", "光", "照"]))
                status, saved = ordinary_edit(db, merged, "replace", 0, draft="晨 光")
            else:
                status, saved = ordinary_edit(db, original, "replace", 0, draft="晨")
            self.assertEqual((status, saved.words, saved.word_beats), (200, original.words, original.word_beats))
            status, _ = ordinary_edit(db, original, "insert", 1, draft="且")
            self.assertEqual(status, 409)

            preview = Page(render_preview(build_preview(db, saved.revision, "1", "2")))
            form = preview.forms["publish-form"]
            entry = publish_edition(db, int(form.hidden["revision"]), form.hidden["first"], form.hidden["last"])
            edition = Page(render_edition(read_edition(db, entry.number)))
            self.assertEqual(edition.revision, saved.revision)
            self.assertEqual(edition.cells, preview.cells)
            self.assertEqual(edition.cells["alto", "1", 0], ("晨 光", False))
            self.assertEqual(edition.cells["sop", "1", 1], ("", True))
            return edition.cells

    def test_existing_operations_on_liandu_sample(self):
        source = json.loads(SAMPLE.read_text(encoding="utf-8"))
        self.assertEqual(self.play_ordinary_history(source, True), self.play_ordinary_history(source, False))


class LianduWebFlowTest(ScoreCase):
    """Drives the new operations through real HTML forms over HTTP and reads editions back by number."""

    def setUp(self):
        super().setUp()
        self.site.import_source(json.loads(SAMPLE.read_text(encoding="utf-8")))

    def worksheet(self, *, revision=None):
        path = worksheet_url(score="liandu" if revision is None else None,
                             revision=revision, voice="sop", bar="1")
        status, page = self.browser.get(path)
        self.assertEqual(status, 200)
        return page

    def post_form(self, page, kind, *indexes, draft=None):
        form = page.forms[f"{kind}-form"]
        fields = dict(form.hidden)
        if kind in ("replace", "resegment"):
            first, last = indexes if len(indexes) == 2 else (indexes[0], indexes[0])
            fields["first"] = form.choices["first"][first]
            fields["last"] = form.choices["last"][last]
            fields["draft"] = "" if draft is None else draft
        elif kind == "insert":
            fields["gap"] = form.choices["gap"][indexes[0]]
            fields["draft"] = draft
        else:
            fields["gap"] = form.choices["gap"][indexes[0]]
        return self.browser.post(form.action, fields)

    def test_resegment_liaison_hide_show_and_edition_readback(self):
        original = self.worksheet()
        # 乙先将前两词重分为「晨光」，码点与拍位不变
        status, merged = self.post_form(original, "resegment", 0, 1, draft="晨光")
        self.assertEqual(status, 200)
        self.assertEqual((merged.words, merged.word_beats),
                         (["晨光", "晨", "光", "照"], [0, 0, 0, 2]))
        # 甲在旧页补标第一、第二词缝：成功但暂隐
        status, marked = self.post_form(original, "liaison", 0)
        self.assertEqual(status, 200)
        self.assertIn("saved-preview", marked.nodes)
        hidden = self.browser.get(marked.nodes["saved-preview"]["href"])[1]
        self.assertEqual(hidden.mark_states, [(1, "hidden")])
        self.assertEqual([item for item in hidden.liaisons if item[0] == "grid"], [])

        # 拆回「晨 光」后仅高声部第一缝复显
        status, split = self.post_form(marked, "resegment", 0, 0, draft="晨 光")
        self.assertEqual(status, 200)
        self.assertEqual(split.liaisons, [("measure", 1)])
        status, visible = self.browser.get(f"/preview?revision={split.revision}&first=1&last=2")
        self.assertEqual(status, 200)
        self.assertEqual(visible.mark_states, [(1, "visible")])
        self.assertEqual(
            [cell for kind, cell in visible.liaisons if kind == "grid"],
            [("sop", "1", 0)],
        )
        # 较早版本仍按各自当时的状态预览
        self.assertEqual(hidden.mark_states, [(1, "hidden")])

        # 可见时签存，再以同字重写使标记永久失效
        form = visible.forms["publish-form"]
        status, edition = self.browser.post(form.action, form.hidden)
        self.assertEqual(status, 201)
        number = edition.nodes["edition"]["data-number"]
        target = split.forms["replace-form"].choices["first"][0]
        status, rewritten = self.browser.post("/edit", {
            "kind": "replace", "voice": "sop", "bar": "1",
            "first": target, "last": target, "draft": "晨",
        })
        self.assertEqual(status, 200)
        status, dead = self.browser.get(f"/preview?revision={rewritten.revision}&first=1&last=1")
        self.assertEqual(dead.mark_states, [(1, "dead")])

        # 重开后按原号领取：连读仍在原位置，拍格与换气照旧
        self.site.restart()
        browser = self.site.browser()
        status, reopened = browser.get(f"/edition?number={number}")
        self.assertEqual(status, 200)
        self.assertEqual(reopened.cells, edition.cells)
        self.assertEqual(reopened.liaisons, edition.liaisons)
        self.assertEqual(
            [cell for kind, cell in reopened.liaisons if kind == "grid"], [("sop", "1", 0)]
        )

    def test_insert_separates_then_restores_and_form_errors(self):
        original = self.worksheet()
        status, marked = self.post_form(original, "liaison", 0)
        self.assertEqual(status, 200)
        old_gap = original.forms["liaison-form"].choices["gap"][0]
        # 插词隔开：已办项暂隐，未办理的原缝表单 409
        status, inserted = self.post_form(marked, "insert", 1, draft="且")
        self.assertEqual(status, 200)
        status, hidden = self.browser.get(f"/preview?revision={inserted.revision}&first=1&last=1")
        self.assertEqual(hidden.mark_states, [(1, "hidden")])
        status, conflict = self.browser.post("/edit", {
            "kind": "liaison", "voice": "sop", "bar": "1", "gap": old_gap,
        })
        self.assertEqual(status, 409)
        self.assertIn("liaison-conflict", conflict.nodes)
        # 普通空替换删词后复显
        target = inserted.forms["replace-form"].choices["first"][1]
        status, restored = self.browser.post("/edit", {
            "kind": "replace", "voice": "sop", "bar": "1",
            "first": target, "last": target, "draft": "",
        })
        self.assertEqual(status, 200)
        self.assertEqual(restored.liaisons, [("measure", 1)])
        # 非法与过时提交不留部分结果
        before = self.site.scalar("SELECT count(*) FROM revisions WHERE score = ?", ("liandu",))
        status, bad_beat = self.post_form(original, "resegment", 3, 4, draft="光照")
        self.assertEqual(status, 400)
        status, bad_code = self.post_form(original, "resegment", 0, 0, draft="辰")
        self.assertEqual(status, 400)
        status, stale = self.post_form(original, "resegment", 2, 3, draft="晨光")
        self.assertEqual(status, 409)
        self.assertEqual(
            self.site.scalar("SELECT count(*) FROM revisions WHERE score = ?", ("liandu",)),
            before,
        )
        self.assertEqual(self.site.scalar("SELECT count(*) FROM liaisons"), 1)


if __name__ == "__main__":
    unittest.main()
