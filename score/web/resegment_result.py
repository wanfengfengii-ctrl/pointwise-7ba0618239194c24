import sqlite3
from html import escape

from score.web.worksheet import render_worksheet


def render_resegment_conflict(
    db: sqlite3.Connection, revision: int, voice: str, bar: str, reason: str
) -> tuple[int, str]:
    notice = (f'<p class="notice conflict" role="alert" id="resegment-conflict">'
              f'重分词冲突。{escape(reason)}。请在当前工作版重新选择。</p>')
    return 409, render_worksheet(db, revision=revision, voice=voice, bar=bar, notice=notice)
