from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from score.edit.commit import (
    EditNotFound,
    InvalidEdit,
    OperationConflict,
    submit_edit,
    submit_resegment,
)
from score.edition.catalogue import list_editions
from score.edition.publish import PublishError, initialize_edition_store, publish_edition
from score.edition.readback import EditionNotFound, read_edition, render_edition
from score.liandu.store import initialize_liaison_store
from score.liandu.submit import LiaisonConflict, LiaisonNotFound, LiaisonSelection, submit_liaison
from score.rehearse.preview import PreviewNotFound, build_preview, render_preview
from score.rehearse.section import InvalidPracticeRange
from score.edit.resegment import ResegmentInvalid
from score.source.bars import read_bars
from score.source.import_score import SourceImportError, import_score, initialize_source_store, list_sources
from score.source.seed import initialize_sample
from score.source.voices import read_voices
from score.web.edit_form import EditFormInput, LiaisonFormInput, decode_edit_form
from score.web.edit_result import render_edit_result
from score.web.liaison_result import render_liaison_conflict, render_liaison_result
from score.web.navigation import edition_url, page, worksheet_url
from score.web.resegment_result import render_resegment_conflict
from score.web.worksheet import WorksheetNotFound, render_worksheet


STYLE = Path(__file__).with_name('style.css')


class RequestError(ValueError):
    pass


def connect_score(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path, timeout=10)
    db.execute('PRAGMA foreign_keys = ON')
    return db


def _fields(raw: str) -> dict[str, str]:
    parsed = parse_qs(raw, keep_blank_values=True, strict_parsing=True, max_num_fields=16, errors='strict')
    if any(len(values) != 1 for values in parsed.values()):
        raise RequestError('请求参数不可重复')
    return {name: values[0] for name, values in parsed.items()}


def _required(fields: dict[str, str], name: str) -> str:
    if not fields.get(name):
        raise RequestError(f'缺少参数 {name}')
    return fields[name]


def _number(fields: dict[str, str], name: str) -> int:
    raw = _required(fields, name)
    try:
        value = int(raw)
    except ValueError as error:
        raise RequestError(f'{name} 必须是正整数') from error
    if not 0 < value < 2**63:
        raise RequestError(f'{name} 超出号码范围')
    return value


def _home(db: sqlite3.Connection) -> str:
    scores = []
    for score, title in list_sources(db):
        voice = read_voices(db, score)[0]
        bar = read_bars(db, score)[0]
        href = escape(worksheet_url(score=score, voice=voice.id, bar=bar.id))
        scores.append(f'<li><a href="{href}">{escape(title)}</a></li>')
    editions = []
    for entry in list_editions(db):
        href = escape(edition_url(entry.number))
        editions.append(f'<li><a href="{href}">定稿 {entry.number}</a> '
                        f'· 工作版 {entry.revision} · 小节 {escape(entry.first)} 至 {escape(entry.last)}</li>')
    catalogue = '<ul>' + ''.join(editions) + '</ul>' if editions else '<p>还没有定稿。</p>'
    return page('工作台', f'<h1>排练谱工作台</h1><h2>工作谱</h2><ul>{"".join(scores)}</ul>'
                            f'<h2>定稿目录</h2>{catalogue}')


class ScoreHandler(BaseHTTPRequestHandler):
    server: ScoreServer

    def _reply(self, status: int, content: str, *, mime: str = 'text/html', location: str | None = None) -> None:
        body = content.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', mime + '; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        if location is not None:
            self.send_header('Location', location)
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, detail: str) -> None:
        self._reply(status, page('请求未完成', f'<h1>请求未完成</h1><p>{escape(detail)}</p>'))

    def _body(self) -> str:
        if self.headers.get_content_type() != 'application/x-www-form-urlencoded':
            raise RequestError('请通过网页表单提交')
        length = int(self.headers.get('Content-Length', '0'))
        if not 0 < length <= 65_536:
            raise RequestError('表单为空或大小超过限制')
        data = self.rfile.read(length)
        if len(data) != length:
            raise RequestError('表单未完整送达')
        return data.decode('utf-8')

    def _get(self, db: sqlite3.Connection, path: str, fields: dict[str, str]) -> None:
        if path == '/':
            self._reply(200, _home(db))
        elif path == '/worksheet':
            revision = _number(fields, 'revision') if 'revision' in fields else None
            self._reply(200, render_worksheet(
                db, revision=revision, score=fields.get('score'),
                voice=_required(fields, 'voice'), bar=_required(fields, 'bar'),
            ))
        elif path == '/preview':
            preview = build_preview(db, _number(fields, 'revision'), _required(fields, 'first'), _required(fields, 'last'))
            self._reply(200, render_preview(preview))
        elif path == '/edition':
            self._reply(200, render_edition(read_edition(db, _number(fields, 'number'))))
        else:
            self._error(404, '页面不存在')

    def _post(self, db: sqlite3.Connection, path: str) -> None:
        if path == '/edit':
            submission = decode_edit_form(self._body())
            if isinstance(submission, LiaisonFormInput):
                selection = LiaisonSelection(
                    submission.revision, submission.voice, submission.bar,
                    submission.left, submission.right,
                )
                try:
                    current, mark = submit_liaison(db, selection)
                except LiaisonConflict as error:
                    status, body = render_liaison_conflict(
                        db, error.revision.number, submission.voice, submission.bar, error.reason
                    )
                    self._reply(status, body)
                    return
                status, body = render_liaison_result(
                    db, current.number, submission.voice, submission.bar, mark
                )
                self._reply(status, body)
                return
            if submission.selection.kind == 'resegment':
                try:
                    result = submit_resegment(db, submission.selection, submission.draft)
                except OperationConflict as error:
                    status, body = render_resegment_conflict(
                        db, error.revision.number, submission.selection.voice,
                        submission.selection.bar, error.reason,
                    )
                    self._reply(status, body)
                    return
            else:
                result = submit_edit(db, submission.selection, submission.draft)
            status, body = render_edit_result(db, result, submission.draft)
            self._reply(status, body)
        elif path == '/edition':
            fields = _fields(self._body())
            entry = publish_edition(db, _number(fields, 'revision'), _required(fields, 'first'), _required(fields, 'last'))
            body = render_edition(read_edition(db, entry.number))
            self._reply(201, body, location=edition_url(entry.number))
        else:
            self._error(404, '页面不存在')

    def _dispatch(self, *, post: bool) -> None:
        try:
            target = urlsplit(self.path)
            if target.path == '/style.css' and not post:
                self._reply(200, STYLE.read_text(encoding='utf-8'), mime='text/css')
                return
            with closing(connect_score(self.server.database)) as db:
                if post:
                    self._post(db, target.path)
                else:
                    self._get(db, target.path, _fields(target.query))
        except (WorksheetNotFound, EditNotFound, PreviewNotFound, EditionNotFound, LiaisonNotFound) as error:
            self._error(404, str(error))
        except (InvalidEdit, InvalidPracticeRange, ResegmentInvalid, ValueError) as error:
            self._error(400, str(error))
        except OperationConflict as error:
            self._error(409, error.reason)
        except LiaisonConflict as error:
            self._error(409, str(error))
        except PublishError as error:
            self.log_error('publish failed: %s', error.__cause__)
            self._error(503, str(error))
        except (sqlite3.Error, OSError) as error:
            if isinstance(error, (BrokenPipeError, ConnectionResetError)):
                return
            self.log_error('request failed: %s', error)
            self._error(503, '服务暂时无法访问排练谱')

    def do_GET(self) -> None:
        self._dispatch(post=False)

    def do_POST(self) -> None:
        self._dispatch(post=True)

    def log_request(self, code='-', size='-') -> None:
        # Expected application-level errors have normal response pages.
        pass


class ScoreServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], database: Path):
        self.database = database
        super().__init__(address, ScoreHandler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='望溪合唱团排练谱')
    parser.add_argument('--db', default='rehearsal.sqlite3', type=Path)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('init', help='登记例谱或领取现行工作版')
    import_command = commands.add_parser('import', help='导入分声部源谱')
    import_command.add_argument('file', type=Path)
    serve = commands.add_parser('serve', help='开启浏览器工作台')
    serve.add_argument('--host', default='127.0.0.1')
    serve.add_argument('--port', type=int, default=8000)
    args = parser.parse_args(argv)
    if args.command == 'serve' and not 0 <= args.port <= 65535:
        parser.error('端口必须在 0 至 65535 之间')
    try:
        with closing(connect_score(args.db)) as db:
            initialize_source_store(db)
            initialize_edition_store(db)
            initialize_liaison_store(db)
            if args.command == 'import':
                revision = import_score(db, json.loads(args.file.read_text(encoding='utf-8')))
            else:
                revision = initialize_sample(db)
        if args.command == 'serve':
            with ScoreServer((args.host, args.port), args.db) as server:
                print(f'LISTEN {server.server_port}', flush=True)
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    pass
        else:
            print(json.dumps({'score': revision.score, 'revision': revision.number}, ensure_ascii=False))
    except (ValueError, OSError, sqlite3.Error) as error:
        parser.exit(2, f'{error}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
