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


def _option(key: list, label: str) -> str:
    value = escape(json.dumps(key, separators=(',', ':')), quote=True)
    return f'<option value="{value}">{escape(label)}</option>'


def _menu(name: str, label: str, options: str) -> str:
    return (f'<label>{label}<select name="{name}" required>'
            f'<option value="">请选择</option>{options}</select></label>')


def _form(kind: str, title: str, voice: str, bar: str, menus: str, draft: str) -> str:
    return f'''<form id="{kind}-form" class="edit-form" method="post" action="/edit">
<h2>{title}</h2>
<input type="hidden" name="kind" value="{kind}">
<input type="hidden" name="voice" value="{escape(voice)}">
<input type="hidden" name="bar" value="{escape(bar)}">
<div class="choices">{menus}</div>
<label>新词<textarea name="draft" rows="2">
{escape(draft)}</textarea></label>
<button type="submit">{title}</button>
</form>'''


def render_edit_form(
    revision: int, voice: str, bar: str, words: tuple[Occurrence, ...], *, draft: str = ''
) -> str:
    result = []
    if words:
        options = ''.join(
            _option([revision, word.key], f'{index + 1}. {word.text}')
            for index, word in enumerate(words)
        )
        menus = _menu('first', '第一词', options) + _menu('last', '最后一词', options)
        result.append(_form('replace', '替换词段', voice, bar, menus, draft))
    gaps = []
    for gap in enumerate_gaps(words):
        left = words[gap.index - 1].text if gap.left is not None else '小节开始'
        right = words[gap.index].text if gap.right is not None else '小节结束'
        gaps.append(_option([revision, gap.left, gap.right], f'{gap.index + 1}. {left} ｜ {right}'))
    result.append(_form('insert', '在缝中插词', voice, bar, _menu('gap', '插入位置', ''.join(gaps)), draft))
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


def decode_edit_form(body: str) -> EditFormInput:
    try:
        parts = parse_qs(body, keep_blank_values=True, strict_parsing=True, max_num_fields=12, errors='strict')
        if any(len(values) != 1 for values in parts.values()):
            raise InvalidEdit('每次提交只可指定一笔编辑')
        fields = {name: values[0] for name, values in parts.items()}
        kind = fields['kind']
        expected = {'kind', 'voice', 'bar', 'draft'}
        if kind == 'replace' and fields.keys() == expected | {'first', 'last'}:
            revision, first = _read_key(fields['first'], 2)
            last_revision, last = _read_key(fields['last'], 2)
            if revision != last_revision or first is None or last is None:
                raise InvalidEdit('替换的两端必须来自同一原页')
        elif kind == 'insert' and fields.keys() == expected | {'gap'}:
            revision, first, last = _read_key(fields['gap'], 3)
        else:
            raise InvalidEdit('请在一个编辑表单中选择词段或缝')
        if not fields['voice'] or not fields['bar']:
            raise InvalidEdit('缺少声部或小节')
        return EditFormInput(EditSelection(revision, fields['voice'], fields['bar'], kind, first, last), fields['draft'])
    except InvalidEdit:
        raise
    except (ValueError, KeyError, RecursionError) as error:
        raise InvalidEdit('表单中的选择不完整，请重新选择') from error
