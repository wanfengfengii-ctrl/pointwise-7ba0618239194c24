import sqlite3
from html import escape

from score.edit.commit import EditConflict, SavedEdit
from score.web.navigation import preview_url
from score.web.worksheet import render_worksheet


def render_edit_result(
    db: sqlite3.Connection, result: SavedEdit | EditConflict, draft: str
) -> tuple[int, str]:
    selection = result.selection
    options = {'revision': result.revision.number, 'voice': selection.voice, 'bar': selection.bar}
    if isinstance(result, SavedEdit):
        preview = escape(preview_url(result.revision.number, selection.bar, selection.bar))
        notice = (f'<p class="notice saved" id="saved" role="status">已保存工作版 {result.revision.number}。 '
                  f'<a id="saved-preview" href="{preview}">预览实际保存版</a></p>')
        return 200, render_worksheet(db, **options, notice=notice)

    if result.start == result.stop:
        position = f'当前第 {result.start + 1} 条缝'
        current_text = '此处没有歌词'
    else:
        position = f'当前第 {result.start + 1} 至 {result.stop} 词'
        current_text = ' '.join(word.text for word in result.words[result.start:result.stop])
    notice = (f'<p class="notice conflict" role="alert" id="edit-conflict" '
              f'data-start="{result.start}" data-stop="{result.stop}">'
              f'编辑冲突。{escape(result.reason)}。{position}：{escape(current_text)}。'
              '请在当前词序重新选择，草稿已保留。</p>')
    return 409, render_worksheet(
        db, **options, notice=notice, draft=draft, conflict=(result.start, result.stop)
    )
