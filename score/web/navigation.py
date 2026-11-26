from html import escape
from urllib.parse import urlencode


def worksheet_url(*, voice: str, bar: str, revision: int | None = None, score: str | None = None) -> str:
    params = {'voice': voice, 'bar': bar}
    if revision is not None:
        params['revision'] = revision
    if score is not None:
        params['score'] = score
    return '/worksheet?' + urlencode(params)


def preview_url(revision: int, first: str, last: str) -> str:
    return '/preview?' + urlencode({'revision': revision, 'first': first, 'last': last})


def edition_url(number: int) -> str:
    return '/edition?' + urlencode({'number': number})


def page(title: str, body: str) -> str:
    return f'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} · 望溪排练谱</title>
<link rel="stylesheet" href="/style.css">
</head>
<body>
<header class="site"><a href="/">望溪排练谱</a></header>
<main>{body}</main>
</body>
</html>'''
