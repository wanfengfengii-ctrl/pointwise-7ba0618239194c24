import sqlite3
from dataclasses import dataclass
from html import escape

from score.edit.revisions import read_revision
from score.rehearse.beat_grid import PracticeGrid, build_beat_grid
from score.rehearse.breath_cues import BreathCue, place_breath_cues
from score.rehearse.section import PracticeSection, resolve_section
from score.source.bars import read_bars
from score.source.import_score import read_source_title
from score.source.voices import read_voices
from score.web.navigation import page, worksheet_url


class PreviewNotFound(LookupError):
    pass


@dataclass(frozen=True)
class PracticePreview:
    score: str
    title: str
    revision: int
    section: PracticeSection
    grid: PracticeGrid
    cues: tuple[BreathCue, ...]


def build_preview(db: sqlite3.Connection, revision: int, first: str, last: str) -> PracticePreview:
    working = read_revision(db, revision)
    if working is None:
        raise PreviewNotFound('工作版不存在')
    section = resolve_section(read_bars(db, working.score), first, last)
    grid = build_beat_grid(working, section, read_voices(db, working.score))
    title = read_source_title(db, working.score)
    return PracticePreview(working.score, title, revision, section, grid, place_breath_cues(grid))


def render_grid(grid: PracticeGrid, cues: tuple[BreathCue, ...]) -> str:
    cues_at = {(cue.voice, cue.column) for cue in cues}
    headings = ''.join(
        f'<th scope="col" data-bar="{escape(column.bar)}" data-beat="{column.beat}">'
        f'{escape(column.bar)} 小节 · {column.beat + 1} 拍</th>'
        for column in grid.columns
    )
    rows = []
    for voice, row in zip(grid.voices, grid.rows):
        cells = []
        for index, (column, cell) in enumerate(zip(grid.columns, row)):
            marked = (voice.id, index) in cues_at
            words = ' '.join(escape(word) for word in cell.words)
            cue = '<small>换气</small>' if marked else ''
            marker = ' data-cue="breath"' if marked else ''
            idle = ' class="rest" aria-label="休止，换气"' if marked else ' class="rest" aria-label="休止"'
            style = idle if not cell.words else ''
            cells.append(f'<td data-bar="{escape(column.bar)}" data-beat="{column.beat}"{style}{marker}>'
                         f'<span class="tokens">{words}</span>{cue}</td>')
        rows.append(f'<tr data-voice="{escape(voice.id)}"><th scope="row">{escape(voice.name)}</th>{"".join(cells)}</tr>')
    return ('<div class="grid-scroll"><table id="practice-grid"><thead><tr>'
            f'<th scope="col">声部</th>{headings}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


def render_preview(preview: PracticePreview) -> str:
    first, last = preview.section.first, preview.section.last
    worksheet = escape(worksheet_url(revision=preview.revision, voice=preview.grid.voices[0].id, bar=first))
    return page('排练预览', f'''
<section id="preview" data-revision="{preview.revision}">
<h1>{escape(preview.title)} · 排练预览</h1>
<p>工作版 {preview.revision} · 小节 {escape(first)} 至 {escape(last)}</p>
{render_grid(preview.grid, preview.cues)}
<form class="toolbar range" method="post" action="/edition" id="publish-form">
<input type="hidden" name="revision" value="{preview.revision}">
<input type="hidden" name="first" value="{escape(first)}">
<input type="hidden" name="last" value="{escape(last)}">
<button type="submit">定稿并生成领取号码</button>
<a href="{worksheet}">回到此工作版</a>
</form>
</section>''')
