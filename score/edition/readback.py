import sqlite3
from dataclasses import dataclass
from html import escape

from score.edition.catalogue import CatalogueEntry, find_edition
from score.edition.snapshot import EditionSnapshot, read_snapshot
from score.rehearse.preview import render_grid
from score.web.navigation import edition_url, page


class EditionNotFound(LookupError):
    pass


@dataclass(frozen=True)
class PublishedEdition:
    catalogue: CatalogueEntry
    snapshot: EditionSnapshot


def read_edition(db: sqlite3.Connection, number: int) -> PublishedEdition:
    entry = find_edition(db, number)
    if entry is None:
        raise EditionNotFound('定稿号码不存在')
    snapshot = read_snapshot(db, number)
    if snapshot is None:
        raise EditionNotFound('定稿正文不可领取')
    return PublishedEdition(entry, snapshot)


def render_edition(edition: PublishedEdition) -> str:
    entry, snapshot = edition.catalogue, edition.snapshot
    return page('排练定稿', f'''
<section id="edition" data-number="{entry.number}" data-revision="{entry.revision}">
<h1>{escape(snapshot.title)} · 定稿 {entry.number}</h1>
<p>源自工作版 {entry.revision} · 小节 {escape(entry.first)} 至 {escape(entry.last)}</p>
{render_grid(snapshot.grid, snapshot.cues)}
<p><a id="edition-link" href="{escape(edition_url(entry.number))}">领取此定稿的固定地址</a></p>
</section>''')
