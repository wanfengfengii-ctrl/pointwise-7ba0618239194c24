import json
import queue
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import closing
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener

from score.edit.revisions import read_current_revision, read_revision
from score.source.seed import SAMPLE
from score.web.app import connect_score
from score.web.navigation import worksheet_url


ROOT = Path(__file__).resolve().parents[1]


@dataclass
class HtmlForm:
    action: str
    hidden: dict[str, str] = field(default_factory=dict)
    choices: dict[str, list[str]] = field(default_factory=dict)
    draft: str = ''


class Page(HTMLParser):
    def __init__(self, body: str):
        super().__init__(convert_charrefs=True)
        self.nodes = {}
        self.forms = {}
        self.words = []
        self.word_beats = []
        self.columns = []
        self.voice_order = []
        self.cells = {}
        self.content = []
        self.form = None
        self.select = None
        self.in_draft = False
        self.in_measure = False
        self.word = False
        self.voice = None
        self.cell = None
        self.in_tokens = False
        self.feed(body)
        self.close()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.nodes[attrs['id']] = attrs
        if tag == 'form' and attrs.get('method') == 'post':
            self.form = HtmlForm(attrs['action'])
            self.forms[attrs['id']] = self.form
        elif self.form is not None and tag == 'input' and attrs.get('type') == 'hidden':
            self.form.hidden[attrs['name']] = attrs['value']
        elif self.form is not None and tag == 'select':
            self.select = attrs['name']
            self.form.choices[self.select] = []
        elif self.select is not None and tag == 'option' and attrs.get('value'):
            self.form.choices[self.select].append(attrs['value'])
        elif self.form is not None and tag == 'textarea' and attrs.get('name') == 'draft':
            self.in_draft = True
        if tag == 'ol' and attrs.get('id') == 'measure-words':
            self.in_measure = True
        elif tag == 'li' and self.in_measure:
            self.word = True
            self.words.append('')
            self.word_beats.append(int(attrs['data-beat']))
        elif tag == 'th' and 'data-bar' in attrs:
            self.columns.append((attrs['data-bar'], int(attrs['data-beat'])))
        elif tag == 'tr' and 'data-voice' in attrs:
            self.voice = attrs['data-voice']
            self.voice_order.append(self.voice)
        elif tag == 'td' and self.voice is not None:
            self.cell = (self.voice, attrs['data-bar'], int(attrs['data-beat']))
            self.cells[self.cell] = ('', attrs.get('data-cue') == 'breath')
        elif tag == 'span' and self.cell is not None and attrs.get('class') == 'tokens':
            self.in_tokens = True

    def handle_endtag(self, tag):
        if tag == 'form':
            self.form = None
        elif tag == 'select':
            self.select = None
        elif tag == 'textarea' and self.in_draft:
            self.form.draft = self.form.draft.removeprefix('\n')
            self.in_draft = False
        elif tag == 'ol':
            self.in_measure = False
        elif tag == 'li':
            self.word = False
        elif tag == 'span':
            self.in_tokens = False
        elif tag == 'td':
            self.cell = None
        elif tag == 'tr':
            self.voice = None

    def handle_data(self, data):
        self.content.append(data)
        if self.in_draft:
            self.form.draft += data
        if self.word:
            self.words[-1] += data
        if self.in_tokens:
            text, cue = self.cells[self.cell]
            self.cells[self.cell] = (text + data, cue)

    def lyrics(self, voice: str, bar: str) -> list[str]:
        return [word for cell_bar, beat in self.columns if cell_bar == bar
                for word in self.cells[voice, cell_bar, beat][0].split()]

    @property
    def revision(self) -> int:
        for name in ('worksheet', 'preview', 'edition'):
            if name in self.nodes:
                return int(self.nodes[name]['data-revision'])
        raise ValueError('response does not identify a working revision')


def choice(page: Page, kind: str, first: int, last: int | None = None, *, draft: str) -> tuple[str, dict]:
    form = page.forms[f'{kind}-form']
    fields = dict(form.hidden, draft=draft)
    if kind == 'insert':
        fields['gap'] = form.choices['gap'][first]
    else:
        fields['first'] = form.choices['first'][first]
        fields['last'] = form.choices['last'][first if last is None else last]
    return form.action, fields


class Browser:
    def __init__(self, port: int):
        self.origin = f'http://127.0.0.1:{port}'
        self.opener = build_opener(ProxyHandler({}))

    def get(self, path: str) -> tuple[int, Page]:
        return self._request(Request(self.origin + path))

    def post(self, path: str, fields: dict) -> tuple[int, Page]:
        data = urlencode(fields).encode('ascii')
        return self._request(Request(self.origin + path, data=data))

    def _request(self, request: Request) -> tuple[int, Page]:
        try:
            result = self.opener.open(request, timeout=15)
        except HTTPError as error:
            result = error
        with result:
            return result.code, Page(result.read().decode('utf-8'))


def sample_source() -> dict:
    return json.loads(SAMPLE.read_text(encoding='utf-8'))


class ScoreFixture:
    def __enter__(self):
        self.temp = tempfile.TemporaryDirectory(prefix='rehearsal-')
        self.directory = Path(self.temp.name)
        self.db = self.directory / 'score.sqlite3'
        self.process = None
        try:
            self.start()
        except BaseException:
            self.__exit__()
            raise
        return self

    def __exit__(self, *_):
        try:
            self.stop()
        finally:
            self.temp.cleanup()

    def argv(self, *args: str) -> list[str]:
        return [sys.executable, '-B', '-m', 'score.web.app', '--db', str(self.db), *args]

    def command(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(self.argv(*args), cwd=ROOT, check=check, capture_output=True,
                              text=True, encoding='utf-8', timeout=20)

    def import_source(self, source: dict, *, check: bool = True) -> subprocess.CompletedProcess:
        path = self.directory / 'incoming.json'
        path.write_text(json.dumps(source, ensure_ascii=False), encoding='utf-8')
        return self.command('import', str(path), check=check)

    def start(self) -> None:
        child = subprocess.Popen(self.argv('serve', '--port', '0'), cwd=ROOT,
                                 stdout=subprocess.PIPE, text=True, encoding='utf-8')
        self.process = child
        ready = queue.Queue(maxsize=1)
        reader = threading.Thread(target=lambda: ready.put(child.stdout.readline()), daemon=True)
        reader.start()
        try:
            line = ready.get(timeout=15).strip()
        except queue.Empty as error:
            raise RuntimeError('HTTP service did not announce a listening port') from error
        prefix, _, port = line.partition(' ')
        if prefix != 'LISTEN' or not port.isdecimal():
            raise RuntimeError(f'HTTP service startup failed: {line!r} (exit {child.poll()})')
        self.port = int(port)

    def stop(self) -> None:
        child = self.process
        if child is None:
            return
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=8)
        child.stdout.close()
        self.process = None

    def restart(self) -> None:
        self.stop()
        self.start()

    def browser(self) -> Browser:
        return Browser(self.port)

    def scalar(self, sql: str, parameters: tuple = ()):
        with closing(connect_score(self.db)) as db:
            return db.execute(sql, parameters).fetchone()[0]

    def work(self, score: str = 'wangxi', revision: int | None = None):
        with closing(connect_score(self.db)) as db:
            return read_revision(db, revision) if revision is not None else read_current_revision(db, score)


class ScoreCase(unittest.TestCase):
    def setUp(self):
        self.site = self.enterContext(ScoreFixture())
        self.browser = self.site.browser()

    def worksheet(self, *, browser=None, score=None, revision=None, voice='sop', bar='1') -> Page:
        path = worksheet_url(voice=voice, bar=bar, score=score or ('wangxi' if revision is None else None),
                             revision=revision)
        status, doc = (browser or self.browser).get(path)
        self.assertEqual(status, 200, ''.join(doc.content))
        return doc

    def submit(self, page: Page, kind: str, first: int, last: int | None = None, *, draft: str, browser=None):
        return (browser or self.browser).post(*choice(page, kind, first, last, draft=draft))

    def formal_words(self, score='wangxi', *, voice='sop', bar='1') -> list[str]:
        revision = self.site.work(score)
        return [word.text for word in revision.line(voice, bar)]


def record_case(case_id, input_data, expected, actual, downstream_expected, downstream_actual, paths, oracle):
    print('POINTWISE_SCENARIO ' + json.dumps({
        'case_id': case_id, 'input': input_data, 'expected': expected, 'actual': actual,
        'downstream_expected': downstream_expected, 'downstream_actual': downstream_actual,
        'code_paths': paths, 'oracle': oracle,
    }, ensure_ascii=False, separators=(',', ':')), flush=True)


def demo() -> None:
    with ScoreFixture() as site:
        alpha, beta = site.browser(), site.browser()
        home_url = worksheet_url(score='wangxi', voice='sop', bar='1')
        alpha_status, alpha_page = alpha.get(home_url)
        beta_status, beta_page = beta.get(home_url)
        if (alpha_status, beta_status) != (200, 200) or alpha_page.words != ['A', 'B', 'C']:
            raise RuntimeError('样例工作台没有返回预期原谱')
        inserted, _ = beta.post(*choice(beta_page, 'insert', 3, draft='Y'))
        status, saved = alpha.post(*choice(alpha_page, 'replace', 1, 2, draft='X'))
        if (inserted, status, saved.words) != (200, 200, ['A', 'X', 'Y']):
            raise RuntimeError('旧页段外合并没有保留 Y')
        status, preview = alpha.get(saved.nodes['saved-preview']['href'])
        if status != 200 or preview.revision != saved.revision or preview.lyrics('sop', '1') != saved.words:
            raise RuntimeError('预览与保存稿不一致')
        form = preview.forms['publish-form']
        status, signed = alpha.post(form.action, form.hidden)
        if status != 201:
            raise RuntimeError('排练定稿未生成')
        site.restart()
        status, reopened = site.browser().get(signed.nodes['edition-link']['href'])
        if status != 200 or reopened.cells != preview.cells or reopened.revision != saved.revision:
            raise RuntimeError('重开后领取的拍格或出处已偏离签存稿')
        print(f'工作版 {saved.revision}：{" ".join(saved.words)}')
        print(f'定稿 {reopened.nodes["edition"]["data-number"]} · 原工作版 {reopened.revision}')
        for voice in reopened.voice_order:
            row = [reopened.cells[voice, bar, beat] for bar, beat in reopened.columns]
            print(voice + '：' + ' ｜ '.join(words or ('休止（换气）' if cue else '休止') for words, cue in row))


if __name__ == '__main__':
    demo()
