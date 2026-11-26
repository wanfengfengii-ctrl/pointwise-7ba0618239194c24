import json
from dataclasses import dataclass
from html import escape
from urllib.parse import parse_qs

from score.edit.commit import EditSelection, InvalidEdit
from score.edit.gaps import enumerate_gaps
from score.edit.occurrences import Occurrence


@dataclass(frozen=True)
class EditFormInput:
    selection: EditSelection
    draft: str


@dataclass(frozen=True)
class LiaisonFormInput:
    revision: int
    voice: str
    bar: str
    left: str
    right: str


def _option(key: list, label: str) -> str:
    value = escape(json.dumps(key, separators=(',', ':')), quote=True)
    return f'<option value="{value}">{escape(label)}</option>'


def _menu(name: str, label: str, options: str) -> str:
    return (f'<label>{label}<select name="{name}" required>'
            f'<option value="">请选择</option>{options}</select></label>')


def _form(kind: str, title: str, voice: str, bar: str, menus: str, draft: str, *, with_draft: bool = True) -> str:
    draft_field = (f'<label>新词<textarea name="draft" rows="2">\n{escape(draft)}</textarea></label>'
                   if with_draft else '')
    return f'''<form id="{kind}-form" class="edit-form" method="post" action="/edit">
<h2>{title}</h2>
<input type="hidden" name="kind" value="{kind}">
<input type="hidden" name="voice" value="{escape(voice)}">
<input type="hidden" name="bar" value="{escape(bar)}">
<div class="choices">{menus}</div>
{draft_field}
<button type="submit">{title}</button>
</form>'''


def _word_options(revision: int, words: tuple[Occurrence, ...]) -> str:
    return ''.join(
        _option([revision, word.key], f'{index + 1}. {word.text}')
        for index, word in enumerate(words)
    )


def render_edit_form(
    revision: int, voice: str, bar: str, words: tuple[Occurrence, ...], *, draft: str = ''
) -> str:
    result = []
    if words:
        options = _word_options(revision, words)
        menus = _menu('first', '第一词', options) + _menu('last', '最后一词', options)
        result.append(_form('replace', '替换词段', voice, bar, menus, draft))
        result.append(_form('resegment', '重分词', voice, bar, menus, draft))
    gaps = []
    for gap in enumerate_gaps(words):
        left = words[gap.index - 1].text if gap.left is not None else '小节开始'
        right = words[gap.index].text if gap.right is not None else '小节结束'
        gaps.append(_option([revision, gap.left, gap.right], f'{gap.index + 1}. {left} ｜ {right}'))
    result.append(_form('insert', '在缝中插词', voice, bar, _menu('gap', '插入位置', ''.join(gaps)), draft))
    liaison_gaps = []
    for index in range(len(words) - 1):
        left, right = words[index], words[index + 1]
        if left.beat == right.beat:
            liaison_gaps.append(_option(
                [revision, left.key, right.key],
                f'{index + 1}. {left.text} ｜ {right.text}（同拍）',
            ))
    if liaison_gaps:
        menus = _menu('gap', '连读词缝', ''.join(liaison_gaps))
        result.append(_form('liaison', '标注连读', voice, bar, menus, '', with_draft=False))
    return '<div class="edit-forms">' + ''.join(result) + '</div>'


def _read_key(value: str, size: int) -> list:
    key = json.loads(value)
    if not isinstance(key, list) or len(key) != size:
        raise InvalidEdit('选择格式无效，请在编辑页重新选择')
    if type(key[0]) is not int or not 0 < key[0] < 2**63:
        raise InvalidEdit('原工作版格式无效')
    if any(item is not None and (not isinstance(item, str) or not item) for item in key[1:]):
        raise InvalidEdit('原选择格式无效')
    return key


def decode_edit_form(body: str):
    try:
        parts = parse_qs(body, keep_blank_values=True, strict_parsing=True, max_num_fields=12, errors='strict')
        if any(len(values) != 1 for values in parts.values()):
            raise InvalidEdit('每次提交只可指定一笔编辑')
        fields = {name: values[0] for name, values in parts.items()}
        kind = fields['kind']
        expected = {'kind', 'voice', 'bar', 'draft'}
        if kind in ('replace', 'resegment') and fields.keys() == expected | {'first', 'last'}:
            revision, first = _read_key(fields['first'], 2)
            last_revision, last = _read_key(fields['last'], 2)
            if revision != last_revision or first is None or last is None:
                raise InvalidEdit('选择的两端必须来自同一原页')
        elif kind == 'insert' and fields.keys() == expected | {'gap'}:
            revision, first, last = _read_key(fields['gap'], 3)
        elif kind == 'liaison' and fields.keys() == {'kind', 'voice', 'bar', 'gap'}:
            revision, first, last = _read_key(fields['gap'], 3)
            if first is None or last is None:
                raise InvalidEdit('连读必须选择小节内相邻的两个词')
        else:
            raise InvalidEdit('请在一个编辑表单中选择词段或缝')
        if not fields['voice'] or not fields['bar']:
            raise InvalidEdit('缺少声部或小节')
        if kind == 'liaison':
            return LiaisonFormInput(revision, fields['voice'], fields['bar'], first, last)
        return EditFormInput(EditSelection(revision, fields['voice'], fields['bar'], kind, first, last),
                             fields['draft'])
    except InvalidEdit:
        raise
    except (ValueError, KeyError, RecursionError) as error:
        raise InvalidEdit('表单中的选择不完整，请重新选择') from error
