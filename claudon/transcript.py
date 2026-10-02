import datetime as dt, json, math, re

SKIP_PREFIX = ('<task-notification', '<local-command', 'This session is being continued',
               '[Request interrupted', '<system-reminder', 'Caveat:')
# built-in slash commands that only drive the CLI UI (no model call), so they don't start a task
SKIP_CMDS = {'clear', 'model', 'help', 'compact', 'config', 'resume', 'exit', 'status', 'cost',
             'login', 'logout', 'permissions', 'mcp', 'agents', 'doctor', 'hooks', 'fast', 'effort',
             'plugin', 'reload-skills', 'context', 'usage', 'ide', 'memory', 'add-dir', 'theme', 'vim',
             'terminal-setup', 'export', 'rename', 'tasks', 'bashes', 'rewind', 'sandbox', 'skills',
             'privacy-settings', 'release-notes', 'upgrade', 'output-style', 'keybindings'}


def ts_of(r):
    s = r.get('timestamp')
    if not isinstance(s, str):
        return None
    try:
        return dt.datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp()
    except ValueError:
        return None


def _finite(s):
    f = float(s)
    if not math.isfinite(f):
        raise ValueError(f'non-finite number {s}')
    return f


def _reject(s):
    raise ValueError(f'invalid JSON constant {s}')


def loads(text):
    """json.loads without NaN/Infinity (or floats that overflow to inf): browsers' JSON.parse rejects them."""
    return json.loads(text, parse_float=_finite, parse_constant=_reject)


def num(x):
    """a usable non-negative count/amount, else 0 (strings, bools, negatives and garbage count as 0)"""
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) and x > 0 else 0


def load(path):
    out = []
    with open(path, encoding='utf-8-sig', errors='replace') as f:     # -sig: tolerate a UTF-8 BOM
        for line in f:
            try:
                r = loads(line)
            except ValueError:
                continue
            if isinstance(r, dict):                     # normalise shape so callers can index freely
                r.setdefault('type', None)
                if not isinstance(r.get('message'), dict):
                    r['message'] = {}
                out.append(r)
    return out


def text_of(c):
    if isinstance(c, str):
        return c
    if not isinstance(c, list):
        return ''
    return ' '.join(str(b.get('text', '')) for b in c if isinstance(b, dict) and b.get('type') == 'text')


def prompt_text(r):
    """Human prompt that starts a task, else None."""
    if r.get('type') != 'user' or r.get('isSidechain') or r.get('isMeta') or r.get('isCompactSummary'):
        return None
    origin = r.get('origin') if isinstance(r.get('origin'), dict) else {}
    if r.get('turnOrigin') == 'task_notification' or origin.get('kind') == 'task-notification':
        return None
    c = (r.get('message') or {}).get('content')
    if isinstance(c, list) and any(isinstance(b, dict) and b.get('type') == 'tool_result' for b in c):
        return None
    t = text_of(c).strip()
    if not t or t.startswith(SKIP_PREFIX):
        return None
    # only a record that *is* a slash command (either tag may come first), not a prompt quoting the markup
    m = re.search(r'<command-name>/?([\w:-]+)', t) if t.startswith(('<command-name>', '<command-message>')) else None
    if m:
        if m.group(1) in SKIP_CMDS:
            return None
        args = re.search(r'<command-args>(.*?)</command-args>', t, re.S)
        return f"/{m.group(1)} {args.group(1).strip() if args else ''}".strip()
    return t


TOKEN_KEYS = ('input_tokens', 'output_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens')


def toks(d):
    """usage-shaped dict -> dict(i, o, cr, c5, c1) with the cache-write split into 5m / 1h."""
    cc = d.get('cache_creation') if isinstance(d.get('cache_creation'), dict) else {}
    cc1, cc5 = num(cc.get('ephemeral_1h_input_tokens')), num(cc.get('ephemeral_5m_input_tokens'))
    total_cc = num(d.get('cache_creation_input_tokens'))
    if cc1 + cc5 != total_cc:
        cc1 = min(cc1, total_cc)
        cc5 = total_cc - cc1
    return dict(i=num(d.get('input_tokens')), o=num(d.get('output_tokens')),
                cr=num(d.get('cache_read_input_tokens')), c5=cc5, c1=cc1)


def usage_of(recs):
    usages = [u if isinstance(u := r['message'].get('usage'), dict) else {} for r in recs]
    best = max(usages, key=lambda u: sum(num(u.get(k)) for k in TOKEN_KEYS))
    # streamed records accumulate iterations[]; the longest list is the complete one
    its = max([u['iterations'] for u in usages if isinstance(u.get('iterations'), list)] or [[]], key=len)
    its = [i for i in its if isinstance(i, dict)]
    if not sum(num(best.get(k)) for k in TOKEN_KEYS):    # some logs keep real numbers only in iterations[]
        main = [i for i in its if i.get('type', 'message') == 'message']
        best = {k: sum(num(i.get(k)) for i in main) for k in TOKEN_KEYS} | {'cache_creation': main[-1].get('cache_creation') if main else None}
    think = max(num(d.get('thinking_tokens')) if isinstance(d := u.get('output_tokens_details'), dict) else 0 for u in usages)
    # advisor sub-calls are billed on top of the top-level usage, which covers only the executor
    adv = [(i['model'] if isinstance(i.get('model'), str) else '?', toks(i)) for i in its if i.get('type') == 'advisor_message']
    return toks(best) | dict(think=think, adv=adv, fast=best.get('speed') == 'fast')
