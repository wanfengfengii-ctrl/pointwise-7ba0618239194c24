import sqlite3
from html import escape

from score.edit.revisions import read_current_revision, read_revision
from score.source.bars import read_bars
from score.source.import_score import read_source_title
from score.source.voices import read_voices
from score.web.edit_form import render_edit_form
from score.web.navigation import page, worksheet_url


class WorksheetNotFound(LookupError):
    pass


def _chooser(label: str, name: str, choices, selected: str) -> str:
    options = []
    for key, caption in choices:
        active = ' selected' if key == selected else ''
        options.append(f'<option value="{escape(key)}"{active}>{escape(caption)}</option>')
    return f'<label>{label}<select name="{name}">{"".join(options)}</select></label>'


def render_worksheet(
    db: sqlite3.Connection, *, voice: str, bar: str, revision: int | None = None,
    score: str | None = None, draft: str = '', notice: str = '',
    conflict: tuple[int, int] | None = None,
) -> str:
    if revision is None:
        working = read_current_revision(db, score) if score is not None else None
    else:
        working = read_revision(db, revision)
    if working is None or (score is not None and working.score != score):
        raise WorksheetNotFound('工作版不存在')
    if (voice, bar) not in working.lines:
        raise WorksheetNotFound('该工作版未登记这一声部小节')

    title = read_source_title(db, working.score)
    voices = read_voices(db, working.score)
    bars = read_bars(db, working.score)
    voice_name = next(item.name for item in voices if item.id == voice)
    words = working.line(voice, bar)
    items = []
    for index, word in enumerate(words):
        marked = ' class="conflicting-word"' if conflict and conflict[0] <= index < conflict[1] else ''
        items.append(f'<li data-beat="{word.beat}"{marked}>{escape(word.text)}</li>')
    empty = '<p>本小节没有歌词。</p>' if not words else ''
    form = render_edit_form(working.number, voice, bar, words, draft=draft)
    switch_voice = _chooser('声部', 'voice', ((item.id, item.name) for item in voices), voice)
    bar_choices = tuple((item.id, f'小节 {item.id}') for item in bars)
    switch_bar = _chooser('小节', 'bar', bar_choices, bar)
    start = _chooser('首小节', 'first', bar_choices, bar)
    end = _chooser('尾小节', 'last', bar_choices, bar)
    latest = escape(worksheet_url(score=working.score, voice=voice, bar=bar))
    return page(title, f'''
<section id="worksheet" data-revision="{working.number}">
<h1>{escape(title)}</h1>
<p>{escape(voice_name)} · 小节 {escape(bar)} · 工作版 {working.number}</p>
{notice}
<form class="toolbar" action="/worksheet" method="get">
<input type="hidden" name="revision" value="{working.number}">
{switch_voice}{switch_bar}<button type="submit">打开小节</button>
<a href="{latest}">打开当前工作版</a>
</form>
<h2>正式词序</h2>
<ol id="measure-words">{''.join(items)}</ol>{empty}
{form}
<form class="toolbar range" action="/preview" method="get">
<input type="hidden" name="revision" value="{working.number}">
{start}{end}<button type="submit">预览排练段</button>
</form>
</section>''')
