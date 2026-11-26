import sqlite3

from score.edition.catalogue import CatalogueEntry, create_catalogue_table, register_edition
from score.edition.snapshot import create_snapshot_table, freeze_preview, write_snapshot
from score.rehearse.preview import build_preview


class PublishError(RuntimeError):
    pass


def initialize_edition_store(db: sqlite3.Connection) -> None:
    with db:
        db.execute('BEGIN IMMEDIATE')
        create_catalogue_table(db)
        create_snapshot_table(db)


def publish_edition(db: sqlite3.Connection, revision: int, first: str, last: str) -> CatalogueEntry:
    try:
        with db:
            db.execute('BEGIN IMMEDIATE')
            preview = build_preview(db, revision, first, last)
            snapshot = freeze_preview(preview)
            entry = register_edition(db, preview.revision, preview.section.first, preview.section.last)
            write_snapshot(db, entry.number, snapshot)
    except sqlite3.Error as error:
        raise PublishError('定稿写入失败，请重新打开预览后重试') from error
    return entry
