import json
import unittest
from contextlib import closing
from pathlib import Path
from urllib.parse import urlencode

from score.edit.commit import submit_edit
from score.edition.publish import initialize_edition_store, publish_edition
from score.edition.readback import read_edition, render_edition
from score.rehearse.preview import build_preview, render_preview
from score.source.import_score import import_score, initialize_source_store
from score.web.app import connect_score
from score.web.edit_form import decode_edit_form
from score.web.edit_result import render_edit_result
from score.web.worksheet import render_worksheet
from tests.support import Page, choice


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


if __name__ == "__main__":
    unittest.main()
