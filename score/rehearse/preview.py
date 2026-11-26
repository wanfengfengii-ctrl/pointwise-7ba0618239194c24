import sqlite3
from dataclasses import dataclass
from html import escape

from score.edit.revisions import read_revision
from score.liandu.state import STATE_LABELS, VISIBLE, MarkState, evaluate_line
from score.liandu.store import read_liaisons
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
class LiaisonCue:
    mark_id: int
    voice: str
    column: int


@dataclass(frozen=True)
class PracticePreview:
    score: str
    title: str
    revision: int
    section: PracticeSection
    grid: PracticeGrid
    cues: tuple[BreathCue, ...]
    marks: tuple[MarkState, ...] = ()
    liaison_cues: tuple[LiaisonCue, ...] = ()


def _line_marks(
    db: sqlite3.Connection, score: str, revision: int, voice: str, bar: str, words
) -> tuple[MarkState, ...]:
    marks = tuple(
        mark for mark in read_liaisons(db, score, voice, bar) if mark.revision <= revision
    )
    return evaluate_line(marks, words)


def visible_liaison_cues(preview: PracticePreview) -> tuple[LiaisonCue, ...]:
    """Visible marks positioned on the grid column where the seam is sung."""
    bar_starts = {}
    cursor = 0
    for bar in preview.section.bars:
        bar_starts[bar.id] = cursor
        cursor += bar.meter.beats
    cues = []
    for state in preview.marks:
        if state.state == VISIBLE:
            column = bar_starts[state.mark.bar] + state.left.beat
            cues.append(LiaisonCue(state.mark.id, state.mark.voice, column))
    return tuple(cues)


def build_preview(db: sqlite3.Connection, revision: int, first: str, last: str) -> PracticePreview:
    working = read_revision(db, revision)
    if working is None:
        raise PreviewNotFound('工作版不存在')
    section = resolve_section(read_bars(db, working.score), first, last)
    voices = read_voices(db, working.score)
    grid = build_beat_grid(working, section, voices)
    title = read_source_title(db, working.score)
    marks = []
    for voice in voices:
        for bar in section.bars:
            marks.extend(_line_marks(
                db, working.score, revision, voice.id, bar.id, working.line(voice.id, bar.id)
            ))
    preview = PracticePreview(
        working.score, title, revision, section, grid, place_breath_cues(grid), tuple(marks)
    )
    return PracticePreview(
        preview.score, preview.title, preview.revision, preview.section,
        preview.grid, preview.cues, preview.marks, visible_liaison_cues(preview)
    )


def render_grid(
    grid: PracticeGrid,
    cues: tuple[BreathCue, ...],
    liaison_cues: tuple[LiaisonCue, ...] = (),
) -> str:
    cues_at = {(cue.voice, cue.column) for cue in cues}
    liaisons_at = {}
    for cue in liaison_cues:
        liaisons_at.setdefault((cue.voice, cue.column), []).append(cue.mark_id)
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
            mark_ids = liaisons_at.get((voice.id, index), [])
            tokens = []
            for word_index, word in enumerate(cell.words):
                if word_index:
                    if mark_ids and word_index <= len(mark_ids):
                        mark_id = mark_ids[word_index - 1]
                        tokens.append(
                            f'<span class="liaison-mark" data-liaison="visible" data-mark="{mark_id}"></span> '
                        )
                    else:
                        tokens.append(' ')
                tokens.append(f'<span class="tokens">{escape(word)}</span>')
            words = ''.join(tokens)
            cue = '<small>换气</small>' if marked else ''
            marker = ' data-cue="breath"' if marked else ''
            idle = ' class="rest" aria-label="休止，换气"' if marked else ' class="rest" aria-label="休止"'
            style = idle if not cell.words else ''
            cells.append(f'<td data-bar="{escape(column.bar)}" data-beat="{column.beat}"{style}{marker}>'
                         f'<span class="tokens">{words}</span>{cue}</td>')
        rows.append(f'<tr data-voice="{escape(voice.id)}"><th scope="row">{escape(voice.name)}</th>{"".join(cells)}</tr>')
    return ('<div class="grid-scroll"><table id="practice-grid"><thead><tr>'
            f'<th scope="col">声部</th>{headings}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


def render_marks(marks: tuple[MarkState, ...], voices: dict[str, str]) -> str:
    if not marks:
        return ''
    items = []
    for state in marks:
        mark = state.mark
        label = STATE_LABELS[state.state]
        left = state.left.text if state.left is not None else '（原字已失）'
        right = state.right.text if state.right is not None else '（原字已失）'
        items.append(
            f'<li class="liaison-state" data-mark="{mark.id}" data-state="{state.state}">'
            f'{escape(voices[mark.voice])} · 小节 {escape(mark.bar)} · '
            f'{escape(left)} 与 {escape(right)} 的连读：<strong>{label}</strong>'
            f'<input type="hidden" name="state" value="{state.state}"></li>'
        )
    return ('<section id="liaison-states"><h2>连读标记状态</h2><ul>' + ''.join(items) + '</ul></section>')


def render_preview(preview: PracticePreview) -> str:
    first, last = preview.section.first, preview.section.last
    worksheet = escape(worksheet_url(revision=preview.revision, voice=preview.grid.voices[0].id, bar=first))
    voice_names = {voice.id: voice.name for voice in preview.grid.voices}
    return page('排练预览', f'''
<section id="preview" data-revision="{preview.revision}">
<h1>{escape(preview.title)} · 排练预览</h1>
<p>工作版 {preview.revision} · 小节 {escape(first)} 至 {escape(last)}</p>
{render_grid(preview.grid, preview.cues, preview.liaison_cues)}
{render_marks(preview.marks, voice_names)}
<form class="toolbar range" method="post" action="/edition" id="publish-form">
<input type="hidden" name="revision" value="{preview.revision}">
<input type="hidden" name="first" value="{escape(first)}">
<input type="hidden" name="last" value="{escape(last)}">
<button type="submit">定稿并生成领取号码</button>
<a href="{worksheet}">回到此工作版</a>
</form>
</section>''')
