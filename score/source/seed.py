import json
import sqlite3
from pathlib import Path

from score.edit.revisions import Revision
from score.source.import_score import SourceImportError, import_score


SAMPLE = Path(__file__).resolve().parents[2] / 'samples' / 'wangxi.json'


def initialize_sample(db: sqlite3.Connection) -> Revision:
    try:
        source = json.loads(SAMPLE.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise SourceImportError('无法读取合唱团样例源谱') from error
    return import_score(db, source, reuse=True)
