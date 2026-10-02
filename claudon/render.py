import json
from importlib import resources

TEMPLATE = resources.files(__package__).joinpath('dashboard.html').read_text(encoding='utf-8')


def render_html(data):
    # escape '<' so transcript text like '</script>' can't close the embedded JSON block
    payload = json.dumps(data, separators=(',', ':'), allow_nan=False)     # NaN would break JSON.parse
    return TEMPLATE.replace('__DATA__', payload.replace('<', '\\u003c'))
