import sqlite3
from html import escape

from score.liandu.store import LiaisonMark
from score.web.navigation import preview_url
from score.web.worksheet import render_worksheet


def render_liaison_result(
    db: sqlite3.Connection, revision: int, voice: str, bar: str, mark: LiaisonMark
) -> tuple[int, str]:
    preview = escape(preview_url(revision, bar, bar))
    notice = (f'<p class="notice saved" id="saved" role="status">连读标注已存入工作版 {revision}。 '
              f'<a id="saved-preview" href="{preview}">预览实际保存版</a></p>')
    return 200, render_worksheet(db, revision=revision, voice=voice, bar=bar, notice=notice)


def render_liaison_conflict(
    db: sqlite3.Connection, revision: int, voice: str, bar: str, reason: str
) -> tuple[int, str]:
    notice = (f'<p class="notice conflict" role="alert" id="liaison-conflict">'
              f'连读办理冲突。{escape(reason)}。请在当前词序重新核对词缝。</p>')
    return 409, render_worksheet(db, revision=revision, voice=voice, bar=bar, notice=notice)
