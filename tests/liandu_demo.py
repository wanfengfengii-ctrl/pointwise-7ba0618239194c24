"""演示「晨光练声」的连读链路：旧页补标、拆回复显、重开领回定稿。"""
import json
from pathlib import Path

from tests.support import ScoreFixture


SAMPLE = Path(__file__).resolve().parents[1] / 'samples' / 'liandu.json'


def post(page, browser, kind, *indexes, draft=None):
    form = page.forms[f'{kind}-form']
    fields = dict(form.hidden)
    if kind in ('replace', 'resegment'):
        first, last = indexes if len(indexes) == 2 else (indexes[0], indexes[0])
        fields['first'] = form.choices['first'][first]
        fields['last'] = form.choices['last'][last]
        fields['draft'] = '' if draft is None else draft
    elif kind == 'insert':
        fields['gap'] = form.choices['gap'][indexes[0]]
        fields['draft'] = draft
    else:
        fields['gap'] = form.choices['gap'][indexes[0]]
    return browser.post(form.action, fields)


def demo() -> None:
    with ScoreFixture() as site:
        site.import_source(json.loads(SAMPLE.read_text(encoding='utf-8')))
        browser = site.browser()
        status, old_page = browser.get('/worksheet?score=liandu&voice=sop&bar=1')
        if status != 200 or old_page.words != ['晨', '光', '晨', '光', '照']:
            raise RuntimeError('晨光练声样例没有返回预期词序')
        print(f'原页词序（工作版 {old_page.revision}）：{" ".join(old_page.words)}')

        # 声部长先把前两词重分为「晨光」，字符身份与拍位照留
        status, merged = post(old_page, browser, 'resegment', 0, 1, draft='晨光')
        if status != 200 or merged.words != ['晨光', '晨', '光', '照']:
            raise RuntimeError('重分词合并失败')
        print(f'重分词后（工作版 {merged.revision}）：{" ".join(merged.words)}')

        # 指挥在旧页补标第一、第二词之间的连读
        status, marked = post(old_page, browser, 'liaison', 0)
        if status != 200:
            raise RuntimeError('旧页连读补标失败')
        print(f'旧页补标成功，实际存入工作版 {marked.revision}（两字已在同一词内，预览为暂隐）')
        status, hidden = browser.get(marked.nodes['saved-preview']['href'])
        if hidden.mark_states != [(1, 'hidden')]:
            raise RuntimeError('并词后连读应暂隐')

        # 把「晨光」拆回「晨 光」，标记在实际词缝复显
        status, split = post(marked, browser, 'resegment', 0, 0, draft='晨 光')
        if status != 200 or split.liaisons != [('measure', 1)]:
            raise RuntimeError('拆回后连读应在第一、第二词之间复显')
        print(f'拆回后（工作版 {split.revision}）：{" ".join(split.words)}，第一词缝出现连读提示')

        # 在可见状态预览并签存
        status, preview = browser.get(f'/preview?revision={split.revision}&first=1&last=2')
        if preview.mark_states != [(1, 'visible')]:
            raise RuntimeError('拆回后连读应可见')
        form = preview.forms['publish-form']
        status, edition = browser.post(form.action, form.hidden)
        if status != 201:
            raise RuntimeError('定稿签存失败')
        number = edition.nodes['edition']['data-number']
        print(f'定稿 {number} 已签存工作版 {split.revision} 的拍格、换气与可见连读')

        # 签存后继续改稿：同字重写使旧标记永久失效
        target = split.forms['replace-form'].choices['first'][0]
        status, rewritten = browser.post('/edit', {
            'kind': 'replace', 'voice': 'sop', 'bar': '1',
            'first': target, 'last': target, 'draft': '晨',
        })
        if status != 200:
            raise RuntimeError('签存后的改稿失败')
        status, dead = browser.get(f'/preview?revision={rewritten.revision}&first=1&last=1')
        if dead.mark_states != [(1, 'dead')]:
            raise RuntimeError('同字重写后旧标记应永久失效')
        print(f'改稿后工作版 {rewritten.revision} 的旧连读标记已永久失效，原定稿不受影响')

        # 重开服务，按原号领取
        site.restart()
        status, reopened = site.browser().get(edition.nodes['edition-link']['href'])
        if status != 200 or reopened.liaisons != edition.liaisons or reopened.cells != edition.cells:
            raise RuntimeError('重开后领取的定稿与签存内容不一致')
        print(f'重开后按定稿号 {number} 领取：连读仍在高声部小节 1 首拍的第一词缝，拍格与换气照旧')
        for voice in reopened.voice_order:
            row = [reopened.cells[voice, bar, beat] for bar, beat in reopened.columns]
            print(voice + '：' + ' ｜ '.join(
                (words + '（含连读）') if (voice, bar, beat) in [c for k, c in reopened.liaisons if k == 'grid']
                else words or ('休止（换气）' if cue else '休止')
                for (words, cue), (bar, beat) in zip(row, reopened.columns)
            ))


if __name__ == '__main__':
    demo()
