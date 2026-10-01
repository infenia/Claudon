#!/usr/bin/env python3
"""Claudon - Claude Code session analytics -> self-contained HTML dashboard.

  claudon [PATH] [-o report.html] [--pricing prices.json] [--open] [--install-plugin]

PATH: a ~/.claude dir, its projects/ dir, one project dir, or a single .jsonl (default ~/.claude).
Stdlib only, single file. Everything is derived from the transcripts; see the notes in the dashboard footer.
"""
import argparse, bisect, collections, datetime as dt, json, re, statistics, sys, webbrowser
from pathlib import Path

# $/MTok: input, output, cache_read, cache_write_5m, cache_write_1h.
# Fitted against `cost-state` records in real transcripts; override with --pricing.
PRICE = {'haiku': (1, 5, .1, 1.25, 2), 'sonnet': (2, 10, .2, 2.5, 4), 'opus': (4, 20, .2, 5, 8)}
AGENT_TOOLS = {'Task', 'Agent'}
USER_TOOLS = {'AskUserQuestion', 'ExitPlanMode'}
SKIP_PREFIX = ('<task-notification', '<local-command', 'This session is being continued',
               '[Request interrupted', '<system-reminder', 'Caveat:')
SKIP_CMDS = {'clear', 'model', 'help', 'compact', 'config', 'resume', 'exit', 'status', 'cost',
             'login', 'logout', 'permissions', 'mcp', 'agents', 'doctor', 'hooks', 'fast', 'effort'}
MAX_SEGS = 1200
IDLE_SPLIT = 1800                                # seconds of silence that ends a task


def price(model):
    m = (model or '').lower()
    for fam, p in PRICE.items():
        if fam in m:
            return p, False
    if 'fable' in m:
        return PRICE['opus'], True            # unknown family: opus rates, flagged as estimate
    return (0, 0, 0, 0, 0), True              # non-Anthropic / synthetic


def ts_of(r):
    s = r.get('timestamp')
    if not isinstance(s, str):
        return None
    try:
        return dt.datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp()
    except ValueError:
        return None


def load(path):
    out = []
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def text_of(c):
    if isinstance(c, str):
        return c
    return ' '.join(b.get('text', '') for b in c or [] if isinstance(b, dict) and b.get('type') == 'text')


def prompt_text(r):
    """Human prompt that starts a task, else None."""
    if r.get('type') != 'user' or r.get('isSidechain') or r.get('isMeta') or r.get('isCompactSummary'):
        return None
    if r.get('turnOrigin') == 'task_notification' or (r.get('origin') or {}).get('kind') == 'task-notification':
        return None
    c = (r.get('message') or {}).get('content')
    if isinstance(c, list) and any(isinstance(b, dict) and b.get('type') == 'tool_result' for b in c):
        return None
    t = text_of(c).strip()
    if not t or t.startswith(SKIP_PREFIX):
        return None
    m = re.match(r'<command-name>/?([\w:-]+)', t)
    if m and m.group(1) in SKIP_CMDS:
        return None
    return t


def usage_of(recs):
    best = max((r['message'].get('usage') or {} for r in recs),
               key=lambda u: sum(u.get(k) or 0 for k in ('input_tokens', 'output_tokens',
                                                         'cache_read_input_tokens', 'cache_creation_input_tokens')))
    keys = ('input_tokens', 'output_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens')
    if not sum(best.get(k) or 0 for k in keys):         # some logs keep real numbers only in iterations[]
        its = [i for i in best.get('iterations') or [] if i.get('type', 'message') == 'message']
        best = {k: sum(i.get(k) or 0 for i in its) for k in keys} | {'cache_creation': its[-1].get('cache_creation') if its else None}
    cc = best.get('cache_creation') or {}
    cc1, cc5 = cc.get('ephemeral_1h_input_tokens') or 0, cc.get('ephemeral_5m_input_tokens') or 0
    total_cc = best.get('cache_creation_input_tokens') or 0
    if cc1 + cc5 != total_cc:
        cc5 = total_cc - cc1
    think = max(((r['message'].get('usage') or {}).get('output_tokens_details') or {}).get('thinking_tokens') or 0
                for r in recs)
    return dict(i=best.get('input_tokens') or 0, o=best.get('output_tokens') or 0,
                cr=best.get('cache_read_input_tokens') or 0, c5=cc5, c1=cc1, think=think)


def tool_desc(inp):
    if not isinstance(inp, dict):
        return ''
    for k in ('command', 'file_path', 'pattern', 'description', 'prompt', 'query', 'url', 'path'):
        if inp.get(k):
            return str(inp[k]).replace('\n', ' ')[:110]
    return ''


def ulen(iv):
    tot, s, e = 0, None, None
    for a, b in sorted(iv):
        if e is None or a > e:
            if e is not None:
                tot += e - s
            s, e = a, b
        else:
            e = max(e, b)
    return tot + (e - s if e is not None else 0)


def analyze_session(sid, proj, files, seen_msgs):
    """files: [(path, is_sub)]. Returns (session dict, [task dicts])."""
    recs = []
    for p, is_sub in files:
        for r in load(p):
            r['_sub'] = is_sub or bool(r.get('isSidechain'))
            r['_ts'] = ts_of(r)
            recs.append(r)
    uuid_ts = {r['uuid']: r['_ts'] for r in recs if r.get('uuid') and r['_ts']}

    # --- API calls (assistant records are streamed one content block per record) ---
    by_msg = collections.OrderedDict()
    for r in recs:
        if r['type'] == 'assistant' and r['_ts'] and (r.get('message') or {}).get('id'):
            by_msg.setdefault(r['message']['id'], []).append(r)
    calls, results = [], {}
    for r in recs:                                      # tool_result lookup
        c = (r.get('message') or {}).get('content')
        if r['type'] == 'user' and isinstance(c, list) and r['_ts']:
            for b in c:
                if isinstance(b, dict) and b.get('type') == 'tool_result':
                    results[b.get('tool_use_id')] = (r['_ts'], bool(b.get('is_error')),
                                                     'interrupted' in str(b.get('content'))[:200].lower())
    for mid, rs in by_msg.items():
        if mid in seen_msgs:                            # forked/resumed sessions copy history
            continue
        rs.sort(key=lambda r: r['_ts'])
        first = rs[0]
        start = uuid_ts.get(first.get('parentUuid')) or first['_ts']
        start = min(start, first['_ts'])
        prev, think_s, tools = start, 0.0, []
        for r in rs:
            blocks = r['message'].get('content') or []
            if any(b.get('type') == 'thinking' for b in blocks if isinstance(b, dict)):
                think_s += r['_ts'] - prev
            prev = r['_ts']
            for b in blocks:
                if isinstance(b, dict) and b.get('type') == 'tool_use':
                    tools.append(dict(id=b['id'], name=b.get('name', '?'), ts=r['_ts'], desc=tool_desc(b.get('input'))))
        u = usage_of(rs)
        model = rs[0]['message'].get('model')
        p, est = price(model)
        cost = (u['i'] * p[0] + u['o'] * p[1] + u['cr'] * p[2] + u['c5'] * p[3] + u['c1'] * p[4]) / 1e6
        calls.append(dict(mid=mid, start=start, end=rs[-1]['_ts'], think_s=think_s, model=model or '?', u=u, cost=cost,
                          est=est, sub=first['_sub'], tools=tools, eff=first.get('effort'),
                          synthetic=model == '<synthetic>', ctx=u['i'] + u['cr'] + u['c5'] + u['c1']))
    seen_msgs.update(c['mid'] for c in calls)

    # --- tasks = human prompts in the main transcript ---
    prompts = [(r['_ts'], prompt_text(r)) for r in recs if not r['_sub'] and r['_ts'] and prompt_text(r)]
    prompts.sort()
    first_call = min((c['start'] for c in calls), default=None)
    if first_call is not None and (not prompts or first_call < prompts[0][0] - 1):
        prompts.insert(0, (first_call, '(session start / resumed without a prompt)'))
    # activity resuming after a long gap with no new prompt (e.g. background wake-ups) is its own task
    times = sorted(r['_ts'] for r in recs if r['_ts'] and r['type'] in ('assistant', 'user'))
    pts = sorted(p[0] for p in prompts)
    for a, b in zip(times, times[1:]):
        if b - a > IDLE_SPLIT and not any(abs(b - x) < 2 for x in pts):
            prompts.append((b, '(resumed activity, no new prompt)'))
    prompts.sort()
    if not prompts:
        return None, []
    starts = [p[0] for p in prompts]
    idx = lambda t: max(0, bisect.bisect_right(starts, t) - 1)
    T = [dict(start=s, prompt=t, calls=[], ends=[s], compacts=[], interrupts=0) for s, t in prompts]
    for c in calls:
        T[idx(c['start'])]['calls'].append(c)
    for r in recs:
        if r['_ts'] and r['type'] in ('assistant', 'user'):
            T[idx(r['_ts'])]['ends'].append(r['_ts'])
        if r['type'] == 'system' and r.get('subtype') == 'compact_boundary' and r['_ts']:
            m = r.get('compactMetadata') or {}
            T[idx(r['_ts'])]['compacts'].append((r['_ts'], (m.get('durationMs') or 0) / 1000, m.get('preTokens') or 0, m.get('postTokens') or 0))
    title = ''
    for r in recs:
        if r['type'] in ('ai-title', 'custom-title'):
            title = r.get('aiTitle') or r.get('customTitle') or title
    cwd = next((r['cwd'] for r in recs if r.get('cwd')), '')
    reported = max((r.get('totalCostUSD') or 0 for r in recs if r['type'] == 'cost-state'), default=0)

    tasks = []
    for n, t in enumerate(T):
        cs = t['calls']
        if not cs:
            continue
        t0, t1 = t['start'], max(max(t['ends']), max(c['end'] for c in cs))
        wall = max(t1 - t0, 0.001)
        clip = lambda a, b: (max(a, t0), min(b, t1))
        mi, ti, ai, ui, tool_stats, tcalls, segs = [], [], [], [], {}, [], []
        for c in cs:
            mi.append(clip(c['start'], c['end']))
            segs.append(['ms' if c['sub'] else 'm', round(c['start'] - t0, 2), round(c['end'] - c['start'], 2),
                         c['model'], round(c['think_s'], 2), c['u']['o']])
            for tu in c['tools']:
                res = results.get(tu['id'])
                st = tool_stats.setdefault(tu['name'], [0, 0, 0.0, 0.0, 0])   # n, err, sum, max, interrupted
                st[0] += 1
                if not res:
                    continue
                d = max(0.0, res[0] - tu['ts'])
                st[1] += res[1]; st[2] += d; st[3] = max(st[3], d); st[4] += res[2]
                (ai if tu['name'] in AGENT_TOOLS else ui if tu['name'] in USER_TOOLS else ti).append(clip(tu['ts'], res[0]))
                segs.append(['ts' if c['sub'] else 'te' if res[1] else 't', round(tu['ts'] - t0, 2), round(d, 2), tu['name'], tu['desc'], 0])
                tcalls.append([tu['name'], round(d, 1), tu['desc'], int(res[1])])
        for ct, dur, pre, post in t['compacts']:
            mi.append(clip(ct - dur, ct))
        mi, ti, ai, ui = [[x for x in l if x[1] > x[0]] for l in (mi, ti, ai, ui)]
        u_m = ulen(mi); u_t = ulen(mi + ti); u_a = ulen(mi + ti + ai); u_u = ulen(mi + ti + ai + ui)
        main = [c for c in cs if not c['sub']]
        models = {}
        for c in cs:
            m = models.setdefault(c['model'], [0, 0.0, 0, 0, 0.0, 0.0, 0, 0, 0])  # calls,cost,out,think_tok,dur,think_s,in,cr,cc
            m[0] += 1; m[1] += c['cost']; m[2] += c['u']['o']; m[3] += c['u']['think']; m[4] += c['end'] - c['start']
            m[5] += c['think_s']; m[6] += c['u']['i']; m[7] += c['u']['cr']; m[8] += c['u']['c5'] + c['u']['c1']
        if len(segs) > MAX_SEGS:
            segs = sorted(sorted(segs, key=lambda s: -s[2])[:MAX_SEGS], key=lambda s: s[1])
        ctx = [[round(c['start'] - t0, 1), c['ctx']] for c in sorted(main, key=lambda c: c['start'])]
        if len(ctx) > 200:
            ctx = ctx[::len(ctx) // 200 + 1]
        tcalls.sort(key=lambda x: -x[1])
        tasks.append(dict(
            id=f'{sid[:8]}#{n}', sid=sid, proj=proj, title=title, prompt=t['prompt'][:600], start=t0, wall=round(wall, 2),
            model_s=round(u_m, 2), tool_s=round(u_t - u_m, 2), agent_s=round(u_a - u_t, 2), user_s=round(u_u - u_a, 2),
            wait_s=round(max(0, wall - u_u), 2),
            calls=len(main), sub_calls=len(cs) - len(main), tools=sum(len(c['tools']) for c in cs),
            think_calls=sum(1 for c in cs if c['think_s'] > 0), think_s=round(sum(c['think_s'] for c in cs), 2),
            think_tok=sum(c['u']['think'] for c in cs), out_tok=sum(c['u']['o'] for c in cs),
            in_tok=sum(c['u']['i'] for c in cs), cr_tok=sum(c['u']['cr'] for c in cs),
            cc_tok=sum(c['u']['c5'] + c['u']['c1'] for c in cs),
            cost=round(sum(c['cost'] for c in cs), 5), sub_cost=round(sum(c['cost'] for c in cs if c['sub']), 5),
            est=any(c['est'] for c in cs), ctx_max=max(c['ctx'] for c in cs), compacts=[[round(ct - t0, 1), dur, pre, post] for ct, dur, pre, post in t['compacts']],
            models=models, tool_stats=tool_stats, slow=tcalls[:6], segs=segs, ctx=ctx,
            efforts=sorted({c['eff'] for c in cs if c['eff']})))
    if not tasks:
        return None, []
    sess = dict(id=sid, proj=proj, cwd=cwd, title=title, start=min(t['start'] for t in tasks),
                end=max(t['start'] + t['wall'] for t in tasks), tasks=len(tasks), reported_cost=round(reported, 4),
                est_cost=round(sum(t['cost'] for t in tasks), 4))
    return sess, tasks


def discover(root):
    root = Path(root).expanduser()
    if root.is_file():
        return root.parent, [root]
    base = root / 'projects' if (root / 'projects').is_dir() else root
    return base, sorted(p for p in base.rglob('*.jsonl') if 'tool-results' not in p.parts)


def build(root):
    base, paths = discover(root)
    groups = collections.defaultdict(list)             # (project, session id) -> files
    for p in paths:
        parts = p.relative_to(base).parts
        proj = parts[0] if len(parts) > 1 else base.name
        sub = 'subagents' in parts
        sid = parts[parts.index('subagents') - 1] if sub else p.stem
        groups[(proj, sid)].append((p, sub))
    sessions, tasks, seen = [], [], set()
    # main transcript first so forked copies lose to the original
    for (proj, sid), files in sorted(groups.items(), key=lambda kv: min(f[0].stat().st_mtime for f in kv[1])):
        s, ts = analyze_session(sid, proj, sorted(files, key=lambda f: f[1]), seen)
        if s:
            sessions.append(s); tasks += ts
    for s in sessions:                                 # friendlier project label from cwd
        s['label'] = Path(s['cwd'].replace('\\', '/')).name or s['proj']
    lab = {s['id']: s['label'] for s in sessions}
    for t in tasks:
        t['proj'] = lab.get(t['sid'], t['proj'])
    tasks.sort(key=lambda t: t['start'])
    return dict(generated=dt.datetime.now().isoformat(timespec='seconds'), root=str(base), files=len(paths),
                price=PRICE, sessions=sessions, tasks=tasks)


def redact(d):
    names = {}
    for t in d['tasks']:
        t['proj'] = names.setdefault(t['proj'], f'project-{len(names) + 1}')
        t['prompt'] = f"Task {t['id']}"; t['title'] = ''
        t['slow'] = [[n, dur, '', e] for n, dur, _, e in t['slow']]
        for sg in t['segs']:
            if sg[0] not in ('m', 'ms'):
                sg[4] = ''
    for x in d['sessions']:
        x['cwd'] = x['title'] = ''; x['label'] = x['proj'] = names.get(x['label'], '')
    d['root'] = '(redacted)'


def render_html(data):
    # escape '<' so transcript text like '</script>' can't close the embedded JSON block
    return TEMPLATE.replace('__DATA__', json.dumps(data, separators=(',', ':')).replace('<', '\\u003c'))


def install_plugin():
    cmd_dir = Path.home() / '.claude' / 'commands'
    cmd_dir.mkdir(parents=True, exist_ok=True)
    plugin_file = cmd_dir / 'claudon.md'
    plugin_content = (
        "---\n"
        "description: Generate and open interactive Claudon analytics dashboard for Claude Code sessions\n"
        "---\n\n"
        "Run `claudon ~/.claude -o cc_report.html --open` or `npx claudon ~/.claude -o cc_report.html --open` to analyze sessions.\n"
    )
    plugin_file.write_text(plugin_content, encoding='utf-8')
    print(f"Successfully installed Claudon slash command to {plugin_file}")
    print("You can now type /claudon inside Claude Code to launch analytics!")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('path', nargs='?', default='~/.claude')
    ap.add_argument('-o', '--out', default='cc_report.html')
    ap.add_argument('--pricing', help='JSON {"family-substring": [in, out, cache_read, write_5m, write_1h]} $/MTok')
    ap.add_argument('--redact', action='store_true', help='strip prompts, titles, paths, commands and project names (safe to share)')
    ap.add_argument('--open', action='store_true')
    ap.add_argument('--install-plugin', action='store_true', help='install /claudon slash command into ~/.claude/commands/')
    a = ap.parse_args()
    if a.install_plugin:
        install_plugin()
        return
    if a.pricing:
        PRICE.update({k: tuple(v) for k, v in json.load(open(a.pricing, encoding='utf-8')).items()})
    data = build(a.path)
    if not data['tasks']:
        sys.exit(f'no analysable sessions under {a.path}')
    if a.redact:
        redact(data)
    Path(a.out).write_text(render_html(data), encoding='utf-8')
    print(f'{len(data["sessions"])} sessions, {len(data["tasks"])} tasks from {data["files"]} files -> {a.out}')
    if a.open:
        webbrowser.open(Path(a.out).resolve().as_uri())



TEMPLATE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Claude Code Analytics</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--fg:#1c2330;--mute:#6b7585;--line:#e3e6ec;--model:#3b82f6;--think:#8b5cf6;--tool:#f59e0b;--agent:#14b8a6;--user:#ec4899;--wait:#cbd2dc;--err:#ef4444;--ok:#10b981}
@media(prefers-color-scheme:dark){:root{--bg:#10131a;--card:#181c26;--fg:#e6e9ef;--mute:#8d97a8;--line:#272d3a;--wait:#3a4252}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif}
header{position:sticky;top:0;z-index:5;background:var(--card);border-bottom:1px solid var(--line);padding:10px 20px;display:flex;gap:14px;align-items:center;flex-wrap:wrap}
h1{font-size:16px;margin:0 8px 0 0}nav button,select,input{font:inherit;color:var(--fg);background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:5px 11px}
nav button{cursor:pointer}nav button.on{background:var(--model);border-color:var(--model);color:#fff}
main{padding:20px;max-width:1500px;margin:auto}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-bottom:18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin-bottom:16px}
.grid .card{margin:0}.k{color:var(--mute);font-size:12px;text-transform:uppercase;letter-spacing:.04em}.v{font-size:24px;font-weight:600}.s{color:var(--mute);font-size:12px}
h2{font-size:14px;margin:0 0 10px}.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:16px}
table{border-collapse:collapse;width:100%}th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:middle}
th{color:var(--mute);font-weight:500;font-size:12px;cursor:pointer;white-space:nowrap;user-select:none}th:hover{color:var(--fg)}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}tr.c{cursor:pointer}tr.c:hover{background:var(--bg)}
.pr{max-width:420px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.bar{display:flex;height:10px;border-radius:5px;overflow:hidden;background:var(--wait);min-width:110px}.bar i{display:block}
.m{background:var(--model)}.th{background:var(--think)}.t{background:var(--tool)}.a{background:var(--agent)}.u{background:var(--user)}.w{background:var(--wait)}.e{background:var(--err)}
.leg span{margin-right:14px;font-size:12px;color:var(--mute)}.leg b{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px}
.hb{height:8px;background:var(--model);border-radius:4px;min-width:1px}
.days{display:flex;align-items:flex-end;gap:2px;height:110px}.days div{flex:1;background:var(--model);min-width:2px;border-radius:2px 2px 0 0}
.find{border-left:4px solid var(--tool);padding:6px 12px;margin:10px 0;background:var(--bg);border-radius:0 6px 6px 0}.find.hi{border-color:var(--err)}.find.lo{border-color:var(--model)}
.find b{display:block}.chip{display:inline-block;margin:4px 6px 0 0;padding:1px 8px;border:1px solid var(--line);border-radius:10px;font-size:12px;cursor:pointer;background:var(--card)}.chip:hover{border-color:var(--model)}
#modal{position:fixed;inset:0;background:#0008;display:none;z-index:10;overflow:auto;padding:30px}#modal>div{background:var(--card);max-width:1200px;margin:auto;border-radius:12px;padding:20px;position:relative}
#x{position:absolute;right:14px;top:10px;cursor:pointer;font-size:22px;color:var(--mute)}
.gantt{position:relative;border:1px solid var(--line);border-radius:6px;margin:8px 0 4px;background:var(--bg)}.lane{position:relative;height:24px;border-bottom:1px dashed var(--line)}
.lane:last-child{border:0}.lane span{position:absolute;top:3px;height:18px;border-radius:3px;min-width:2px;opacity:.9}.lane label{position:absolute;left:4px;top:4px;font-size:11px;color:var(--mute);z-index:1;pointer-events:none}
.axis{display:flex;justify-content:space-between;color:var(--mute);font-size:11px}.pre{white-space:pre-wrap;background:var(--bg);padding:10px;border-radius:6px;max-height:160px;overflow:auto;font-size:12px}
footer{color:var(--mute);font-size:12px;padding:10px 20px 40px;max-width:1500px;margin:auto}code{background:var(--bg);padding:1px 5px;border-radius:4px}
.tip{color:var(--mute);cursor:help;border-bottom:1px dotted}
</style></head><body>
<header><h1>Claude Code Analytics</h1>
<nav id="nav"></nav><span style="flex:1"></span>
<select id="fp"></select><input id="fq" placeholder="search prompts…" size="22"></header>
<main id="view"></main><div id="modal"><div><span id="x">×</span><div id="mbody"></div></div></div>
<footer id="foot"></footer>
<script id="d" type="application/json">__DATA__</script>
<script>
window.onerror=(m,u,l)=>{document.body.insertAdjacentHTML('afterbegin','<pre style="color:#c00;padding:16px">Dashboard error: '+m+' (line '+l+')</pre>')};
const D=JSON.parse(document.getElementById('d').textContent);
const $=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const T=s=>{s=Math.round(s);if(s<60)return s+'s';const m=Math.floor(s/60);if(m<60)return m+'m '+s%60+'s';return Math.floor(m/60)+'h '+m%60+'m'};
const N=n=>n>=1e9?(n/1e9).toFixed(2)+'B':n>=1e6?(n/1e6).toFixed(2)+'M':n>=1e3?(n/1e3).toFixed(1)+'k':String(Math.round(n));
const $$=n=>'$'+(n>=100?n.toFixed(0):n.toFixed(2)),P=x=>(x*100).toFixed(0)+'%';
const sum=(a,f)=>a.reduce((s,x)=>s+f(x),0);
const Q=(a,p)=>{if(!a.length)return 0;a=[...a].sort((x,y)=>x-y);return a[Math.min(a.length-1,Math.floor(p*a.length))]};
const date=t=>new Date(t*1000).toISOString().slice(0,10);
const sn=m=>m.replace('claude-','').replace(/-2025\d+$/,'');
const tabs=['Overview','Tasks','Tools','Models & thinking','Bottlenecks'];let cur,tab=0,sorts={},F=[];
$('#nav').innerHTML=tabs.map((t,i)=>`<button data-t="${i}">${t}</button>`).join('');
const projs=[...new Set(D.tasks.map(t=>t.proj))].sort();
$('#fp').innerHTML='<option value="">All projects ('+projs.length+')</option>'+projs.map(p=>`<option>${esc(p)}</option>`).join('');
function filt(){const p=$('#fp').value,q=$('#fq').value.toLowerCase();F=D.tasks.filter(t=>(!p||t.proj==p)&&(!q||(t.prompt+t.title).toLowerCase().includes(q)))}
const bar=t=>{const w=t.wall||1,seg=(k,c)=>`<i class="${c}" style="width:${t[k]/w*100}%" title="${c}"></i>`;
 return `<div class="bar" title="model ${T(t.model_s)} · tools ${T(t.tool_s)} · subagent ${T(t.agent_s)} · user ${T(t.user_s)} · idle ${T(t.wait_s)}">${seg('model_s','m')}${seg('tool_s','t')}${seg('agent_s','a')}${seg('user_s','u')}</div>`};
const legend='<div class="leg"><span><b class="m"></b>model</span><span><b class="th"></b>thinking</span><span><b class="t"></b>tools</span><span><b class="a"></b>subagent wait</span><span><b class="u"></b>user prompts</span><span><b class="w"></b>idle / waiting</span></div>';
function tbl(id,cols,rows,limit=200,click){
 const s=sorts[id]||(sorts[id]={i:cols.findIndex(c=>c.d),d:-1});
 if(s.i>=0){const c=cols[s.i];rows=[...rows].sort((a,b)=>{const x=c.v(a),y=c.v(b);return (x>y?1:x<y?-1:0)*s.d})}
 return `<table><tr>${cols.map((c,i)=>`<th class="${c.n?'n':''}" data-s="${id}|${i}">${c.h}${s.i==i?(s.d<0?' ▾':' ▴'):''}</th>`).join('')}</tr>`+
 rows.slice(0,limit).map(r=>`<tr class="${click?'c':''}" ${click?`data-task="${click(r)}"`:''}>${cols.map(c=>`<td class="${c.n?'n':''}">${c.f(r)}</td>`).join('')}</tr>`).join('')+'</table>'+
 (rows.length>limit?`<div class="s">showing ${limit} of ${rows.length}</div>`:'')}
const kpi=(k,v,s='')=>`<div class="card"><div class="k">${k}</div><div class="v">${v}</div><div class="s">${s}</div></div>`;
const A=a=>({wall:sum(a,t=>t.wall),model:sum(a,t=>t.model_s),tool:sum(a,t=>t.tool_s),agent:sum(a,t=>t.agent_s),user:sum(a,t=>t.user_s),wait:sum(a,t=>t.wait_s),
 calls:sum(a,t=>t.calls),sub:sum(a,t=>t.sub_calls),tools:sum(a,t=>t.tools),cost:sum(a,t=>t.cost),think:sum(a,t=>t.think_s),thinkTok:sum(a,t=>t.think_tok),
 out:sum(a,t=>t.out_tok),inp:sum(a,t=>t.in_tok),cr:sum(a,t=>t.cr_tok),cc:sum(a,t=>t.cc_tok)});
function toolAgg(a){const m={};a.forEach(t=>Object.entries(t.tool_stats).forEach(([k,v])=>{const x=m[k]||(m[k]=[k,0,0,0,0,0]);x[1]+=v[0];x[2]+=v[1];x[3]+=v[2];x[4]=Math.max(x[4],v[3]);x[5]+=v[4]}));return Object.values(m)}
function modelAgg(a){const m={};a.forEach(t=>Object.entries(t.models).forEach(([k,v])=>{const x=m[k]||(m[k]=[k,0,0,0,0,0,0,0,0,0]);for(let i=0;i<9;i++)x[i+1]+=v[i]}));return Object.values(m)}

function overview(){const a=A(F),sess=new Set(F.map(t=>t.sid)).size,cacheHit=a.cr/Math.max(1,a.cr+a.inp+a.cc);
 const days={};F.forEach(t=>days[date(t.start)]=(days[date(t.start)]||0)+t.cost);const dk=Object.keys(days).sort(),mx=Math.max(...Object.values(days),.01);
 const dist=(h,f,fmt)=>`<tr><td>${h}</td><td class="n">${fmt(Q(F.map(f),.5))}</td><td class="n">${fmt(Q(F.map(f),.9))}</td><td class="n">${fmt(Math.max(...F.map(f)))}</td></tr>`;
 const byP={};F.forEach(t=>(byP[t.proj]=byP[t.proj]||[]).push(t));
 return `<div class="grid">${kpi('Tasks',F.length,sess+' sessions')}${kpi('API turns',N(a.calls),N(a.sub)+' by subagents')}${kpi('Tool calls',N(a.tools))}
 ${kpi('Wall time',T(a.wall),'sum over tasks')}${kpi('Model time',T(a.model),P(a.model/a.wall)+' of wall')}${kpi('Thinking time',T(a.think),P(a.think/Math.max(1,a.model))+' of model time')}
 ${kpi('Est. cost',$$(a.cost),$$(a.cost/F.length)+' / task')}${kpi('Output tokens',N(a.out),'thinking '+N(a.thinkTok)+' (where reported)')}${kpi('Cache hit',P(cacheHit),'of input-side tokens')}</div>
 <div class="card"><h2>Where the wall-clock time goes</h2>${bar({wall:a.wall,model_s:a.model,tool_s:a.tool,agent_s:a.agent,user_s:a.user,wait_s:a.wait})}<div style="height:8px"></div>${legend}
 <div class="s" style="margin-top:6px">model ${T(a.model)} (${P(a.model/a.wall)}) · tools ${T(a.tool)} (${P(a.tool/a.wall)}) · subagent wait ${T(a.agent)} · user prompts ${T(a.user)} · idle ${T(a.wait)} (${P(a.wait/a.wall)})</div></div>
 <div class="cols"><div class="card"><h2>Per-task distribution</h2><table><tr><th></th><th class="n">median</th><th class="n">p90</th><th class="n">max</th></tr>
 ${dist('API turns',t=>t.calls,N)}${dist('Tool calls',t=>t.tools,N)}${dist('Wall time',t=>t.wall,T)}${dist('Thinking time',t=>t.think_s,T)}${dist('Cost',t=>t.cost,$$)}${dist('Peak context',t=>t.ctx_max,N)}</table></div>
 <div class="card"><h2>Cost per day</h2><div class="days">${dk.map(d=>`<div title="${d}: ${$$(days[d])}" style="height:${days[d]/mx*100}%"></div>`).join('')}</div><div class="axis"><span>${dk[0]}</span><span>${dk.at(-1)}</span></div></div></div>
 <div class="cols"><div class="card"><h2>Cost by project</h2>${tbl('proj',[{h:'Project',f:r=>esc(r[0]),v:r=>r[0]},{h:'Tasks',n:1,f:r=>r[1],v:r=>r[1]},{h:'Wall',n:1,f:r=>T(r[3]),v:r=>r[3]},{h:'Cost',n:1,d:1,f:r=>$$(r[2]),v:r=>r[2]}],Object.entries(byP).map(([k,v])=>[k,v.length,sum(v,t=>t.cost),sum(v,t=>t.wall)]),15)}</div>
 <div class="card"><h2>Token cost mix</h2>${costMix()}</div></div>`}
function costMix(){const r={in:0,out:0,cr:0,cc:0};D.tasks.filter(t=>F.includes(t)).forEach(t=>Object.entries(t.models).forEach(([m,v])=>{const p=pr(m);r.in+=v[6]*p[0];r.out+=v[2]*p[1];r.cr+=v[7]*p[2];r.cc+=v[8]*p[4]*.8}));
 const tot=sum(Object.values(r),x=>x)||1;return Object.entries({'Output':r.out,'Cache read':r.cr,'Cache write':r.cc,'Fresh input':r.in}).map(([k,v])=>`<div style="display:flex;gap:10px;align-items:center;margin:6px 0"><span style="width:90px">${k}</span><div class="hb" style="width:${v/tot*60}%"></div><span class="s">${P(v/tot)}</span></div>`).join('')+'<div class="s">approximate split (cache writes priced at ~1h/5m blend)</div>'}
const pr=m=>{m=m.toLowerCase();for(const k in D.price)if(m.includes(k))return D.price[k];return m.includes('fable')?D.price.opus:[0,0,0,0,0]};

function tasksView(){return `<div class="card">${legend}<div style="height:8px"></div>`+tbl('tasks',[
 {h:'Date',f:t=>date(t.start),v:t=>t.start,d:1},{h:'Project',f:t=>esc(t.proj),v:t=>t.proj},{h:'Task',f:t=>`<div class="pr" title="${esc(t.prompt)}">${esc(t.prompt)}</div>`,v:t=>t.prompt},
 {h:'Wall',n:1,f:t=>T(t.wall),v:t=>t.wall},{h:'<span class="tip" title="API round-trips by the main agent">Turns</span>',n:1,f:t=>t.calls+(t.sub_calls?` <span class="s">+${t.sub_calls}</span>`:''),v:t=>t.calls},
 {h:'Tools',n:1,f:t=>t.tools,v:t=>t.tools},{h:'Think',n:1,f:t=>T(t.think_s),v:t=>t.think_s},{h:'Think tok',n:1,f:t=>N(t.think_tok),v:t=>t.think_tok},
 {h:'Time split',f:bar,v:t=>t.wait_s/t.wall},{h:'Peak ctx',n:1,f:t=>N(t.ctx_max),v:t=>t.ctx_max},{h:'Cost',n:1,f:t=>$$(t.cost)+(t.est?'*':''),v:t=>t.cost}],F,300,t=>t.id)+'</div>'}

function toolsView(){const rows=toolAgg(F),tot=sum(rows,r=>r[3])||1,mx=Math.max(...rows.map(r=>r[3]),1);
 const slow=F.flatMap(t=>t.slow.map(s=>[...s,t])).sort((a,b)=>b[1]-a[1]).slice(0,25);
 return `<div class="card"><h2>Tools by total time</h2>`+tbl('tools',[{h:'Tool',f:r=>esc(r[0]),v:r=>r[0]},{h:'Calls',n:1,f:r=>N(r[1]),v:r=>r[1]},{h:'Errors',n:1,f:r=>r[2]?`${r[2]} <span class="s">(${P(r[2]/r[1])})</span>`:'–',v:r=>r[2]/r[1]},
 {h:'Total time',n:1,d:1,f:r=>T(r[3]),v:r=>r[3]},{h:'',f:r=>`<div class="hb t" style="width:${r[3]/mx*100}%"></div>`,v:r=>r[3]},{h:'Avg',n:1,f:r=>(r[3]/r[1]).toFixed(1)+'s',v:r=>r[3]/r[1]},{h:'Max',n:1,f:r=>T(r[4]),v:r=>r[4]},{h:'% of tool time',n:1,f:r=>P(r[3]/tot),v:r=>r[3]}],rows,60)+
 `<div class="s">Tool duration = tool_use → tool_result timestamps, so it includes time spent waiting on permission prompts. Subagent (Task/Agent) calls are counted here but painted separately in the time split.</div></div>
 <div class="card"><h2>Slowest individual calls</h2>`+tbl('slow',[{h:'Tool',f:r=>esc(r[0]),v:r=>r[0]},{h:'Duration',n:1,d:1,f:r=>T(r[1]),v:r=>r[1]},{h:'Input',f:r=>`<div class="pr">${esc(r[2])}</div>`,v:r=>r[2]},{h:'Err',f:r=>r[3]?'✗':'',v:r=>r[3]},{h:'Task',f:r=>`<span class="chip" data-task="${r[4].id}">${esc(r[4].prompt.slice(0,50))}</span>`,v:r=>r[4].prompt}],slow,25)+'</div>'}

function modelsView(){const rows=modelAgg(F),a=A(F);
 return `<div class="card"><h2>Models</h2>`+tbl('models',[{h:'Model',f:r=>esc(sn(r[0])),v:r=>r[0]},{h:'Calls',n:1,f:r=>N(r[1]),v:r=>r[1]},{h:'Cost',n:1,d:1,f:r=>$$(r[2]),v:r=>r[2]},{h:'Output tok',n:1,f:r=>N(r[3]),v:r=>r[3]},
 {h:'Thinking tok',n:1,f:r=>N(r[4]),v:r=>r[4]},{h:'Avg call',n:1,f:r=>(r[5]/r[1]).toFixed(1)+'s',v:r=>r[5]/r[1]},{h:'Out tok/s',n:1,f:r=>r[5]?(r[3]/r[5]).toFixed(0):'–',v:r=>r[3]/r[5]},
 {h:'Thinking time',n:1,f:r=>T(r[6]),v:r=>r[6]},{h:'Think / call time',n:1,f:r=>P(r[6]/Math.max(.1,r[5])),v:r=>r[6]/r[5]},{h:'Fresh in',n:1,f:r=>N(r[7]),v:r=>r[7]},{h:'Cache read',n:1,f:r=>N(r[8]),v:r=>r[8]},{h:'Cache write',n:1,f:r=>N(r[9]),v:r=>r[9]}],rows)+'</div>'+
 `<div class="card"><h2>Thinking</h2><div class="grid" style="margin:0">${kpi('Thinking time',T(a.think),P(a.think/Math.max(1,a.model))+' of model time')}${kpi('Thinking tokens',N(a.thinkTok),P(a.thinkTok/Math.max(1,a.out))+' of output (where reported)')}
 ${kpi('Calls with thinking',N(sum(F,t=>t.think_calls)),P(sum(F,t=>t.think_calls)/Math.max(1,a.calls+a.sub))+' of calls')}</div>
 <div class="s" style="margin-top:8px">Thinking text is redacted in the transcripts, so thinking time is measured as the gap between a request and its thinking block being written; tokens come from <code>usage.output_tokens_details.thinking_tokens</code> when the log has it.</div>
 <h2 style="margin-top:14px">Most thinking-heavy tasks</h2>`+tbl('think',[{h:'Task',f:t=>`<div class="pr">${esc(t.prompt)}</div>`,v:t=>t.prompt},{h:'Think time',n:1,d:1,f:t=>T(t.think_s),v:t=>t.think_s},{h:'% of model time',n:1,f:t=>P(t.think_s/Math.max(1,t.model_s)),v:t=>t.think_s/Math.max(1,t.model_s)},{h:'Think tok',n:1,f:t=>N(t.think_tok),v:t=>t.think_tok},{h:'Wall',n:1,f:t=>T(t.wall),v:t=>t.wall}],F,15,t=>t.id)+'</div>'}

function bottlenecks(){const a=A(F),out=[],ids=(l,n=6)=>l.slice(0,n).map(t=>t.id),top=(f,n=5)=>[...F].sort((x,y)=>f(y)-f(x)).slice(0,n);
 const cats=[['model inference',a.model],['tool execution',a.tool],['subagent waits',a.agent],['idle / waiting',a.wait]].sort((x,y)=>y[1]-x[1]);
 out.push(['lo',`Biggest time sink: ${cats[0][0]} (${P(cats[0][1]/a.wall)} of wall time)`,`Breakdown: ${cats.map(c=>c[0]+' '+P(c[1]/a.wall)).join(' · ')}.`,[]]);
 const idle=F.filter(t=>t.wall>60&&t.wait_s/t.wall>.4);if(idle.length)out.push(['hi',`${idle.length} tasks were mostly idle (>40% of time with no model or tool activity)`,`Typically permission prompts, a person reading, background jobs, or hook/startup latency. Total idle ${T(sum(idle,t=>t.wait_s))}. Worst offenders:`,ids(top(t=>t.wait_s).filter(t=>idle.includes(t)))]);
 const tr=toolAgg(F).sort((x,y)=>y[3]-x[3]);if(tr.length)out.push(['',`Slowest tool category: ${tr[0][0]} — ${T(tr[0][3])} total (${P(tr[0][3]/Math.max(1,a.tool+a.agent))} of tool time)`,`Avg ${(tr[0][3]/tr[0][1]).toFixed(1)}s over ${tr[0][1]} calls, max ${T(tr[0][4])}. Next: ${tr.slice(1,4).map(r=>r[0]+' '+T(r[3])).join(', ')}.`,[]]);
 const bad=toolAgg(F).filter(r=>r[1]>=8&&r[2]/r[1]>.15).sort((x,y)=>y[2]/y[1]-x[2]/x[1]);if(bad.length)out.push(['hi','Tools with high failure rates (retry churn)',bad.slice(0,5).map(r=>`${r[0]}: ${r[2]}/${r[1]} failed (${P(r[2]/r[1])})`).join(' · ')+'. Each failure usually costs another full model round-trip.',ids(top(t=>sum(Object.values(t.tool_stats),v=>v[1]))) ]);
 const big=F.filter(t=>t.ctx_max>400000);if(big.length)out.push(['hi',`${big.length} tasks grew context past 400k tokens`,`Every extra turn re-reads the whole context (cache reads) — these tasks cost ${$$(sum(big,t=>t.cost))} (${P(sum(big,t=>t.cost)/a.cost)} of spend). Compact or split them earlier.`,ids(top(t=>t.ctx_max).filter(t=>big.includes(t)))]);
 const th=F.filter(t=>t.model_s>30&&t.think_s/t.model_s>.35);if(th.length)out.push(['',`${th.length} tasks spent >35% of model time thinking`,`Total ${T(sum(th,t=>t.think_s))}. Lowering effort level or giving more precise prompts would shorten these.`,ids(top(t=>t.think_s).filter(t=>th.includes(t)))]);
 const many=top(t=>t.calls);out.push(['',`Most turns for a single task: ${many[0].calls} API round-trips`,`Median task takes ${Q(F.map(t=>t.calls),.5)} turns, p90 ${Q(F.map(t=>t.calls),.9)}. Long tails usually mean exploration loops or rework.`,ids(many)]);
 const cmp=sum(F,t=>t.compacts.length);if(cmp)out.push(['',`${cmp} context compactions`,`Total compaction time ${T(sum(F,t=>sum(t.compacts,c=>c[1])))}; each one discards history the agent may need to re-read.`,ids(F.filter(t=>t.compacts.length))]);
 const sorted=[...F].sort((x,y)=>y.cost-x.cost),k=Math.max(1,Math.ceil(F.length*.05)),topc=sum(sorted.slice(0,k),t=>t.cost);
 out.push(['',`Cost is concentrated: top ${k} task${k>1?'s':''} (5%) = ${P(topc/a.cost)} of spend`,`${$$(topc)} of ${$$(a.cost)}.`,ids(sorted)]);
 const slow=top(t=>t.wall);out.push(['',`Longest tasks by wall time`,'',ids(slow)]);
 return `<div class="card"><h2>Automatic findings</h2>`+out.map(([c,h,b,l])=>`<div class="find ${c}"><b>${esc(h)}</b>${esc(b)}<div>${l.map(id=>{const t=D.tasks.find(x=>x.id==id);return `<span class="chip" data-task="${id}">${esc(t.prompt.slice(0,45))} · ${T(t.wall)} · ${$$(t.cost)}</span>`}).join('')}</div></div>`).join('')+'</div>'}

function detail(id){const t=D.tasks.find(x=>x.id==id),w=t.wall,pc=x=>(x/w*100).toFixed(3)+'%';
 const lanes=[['model','m ms'],['tools','t te ts'],['subagent','ms ts']].map(([n],i)=>`<div class="lane"><label>${n}</label>`+t.segs.filter(s=>i==0?s[0]=='m':i==1?(s[0]=='t'||s[0]=='te'):(s[0]=='ms'||s[0]=='ts')).map(s=>{
  const col=s[0]=='te'?'e':(s[0]=='m'||s[0]=='ms')?'m':s[0]=='ts'?'a':'t',extra=s[0][0]=='m'?`${sn(s[3])} · ${s[5]} out tok · think ${T(s[4])}`:esc(s[3]+': '+s[4]);
  const th=s[0][0]=='m'&&s[4]>0?`<span class="th" style="left:${pc(s[1])};width:${pc(Math.min(s[4],s[2]))}" title="thinking ${T(s[4])}"></span>`:'';
  return `<span class="${col}" style="left:${pc(s[1])};width:${pc(s[2])}" title="${T(s[2])} — ${extra}"></span>${th}`}).join('')+'</div>').join('');
 const ctxMax=Math.max(...t.ctx.map(c=>c[1]),1),svg=t.ctx.length>1?`<svg viewBox="0 0 400 60" width="100%" height="60" preserveAspectRatio="none"><polyline fill="none" stroke="var(--model)" stroke-width="1.5" points="${t.ctx.map(c=>`${c[0]/w*400},${58-c[1]/ctxMax*54}`).join(' ')}"/></svg>`:'';
 const trows=Object.entries(t.tool_stats).map(([k,v])=>[k,...v]);
 return `<h2 style="font-size:16px">${esc(t.title||'Task')} <span class="s">· ${esc(t.proj)} · ${new Date(t.start*1000).toLocaleString()} · ${t.id}</span></h2><div class="pre">${esc(t.prompt)}</div>
 <div class="grid" style="margin:12px 0">${kpi('Wall',T(w))}${kpi('Turns',t.calls,t.sub_calls+' subagent calls')}${kpi('Tool calls',t.tools)}${kpi('Thinking',T(t.think_s),N(t.think_tok)+' tok')}${kpi('Cost',$$(t.cost)+(t.est?'*':''),'subagents '+$$(t.sub_cost))}${kpi('Peak context',N(t.ctx_max),t.compacts.length+' compactions')}</div>
 ${bar(t)}<div style="height:6px"></div>${legend}<h2 style="margin-top:14px">Timeline <span class="s">(purple = thinking portion of a model call, red = failed tool)</span></h2><div class="gantt">${lanes}</div><div class="axis">${[0,.25,.5,.75,1].map(f=>`<span>${T(w*f)}</span>`).join('')}</div>
 <div class="cols" style="margin-top:14px"><div><h2>Tools in this task</h2>${tbl('dt',[{h:'Tool',f:r=>esc(r[0]),v:r=>r[0]},{h:'Calls',n:1,f:r=>r[1],v:r=>r[1]},{h:'Err',n:1,f:r=>r[2],v:r=>r[2]},{h:'Total',n:1,d:1,f:r=>T(r[3]),v:r=>r[3]},{h:'Max',n:1,f:r=>T(r[4]),v:r=>r[4]}],trows,20)}</div>
 <div><h2>Slowest calls</h2>${tbl('ds',[{h:'Tool',f:r=>esc(r[0]),v:r=>r[0]},{h:'Dur',n:1,f:r=>T(r[1]),v:r=>r[1]},{h:'Input',f:r=>`<div class="pr" style="max-width:300px">${esc(r[2])}</div>`,v:r=>r[2]}],t.slow,6)}
 <h2 style="margin-top:12px">Context size per turn</h2>${svg}<div class="s">peak ${N(t.ctx_max)} tokens</div></div></div>`}

const views=[overview,tasksView,toolsView,modelsView,bottlenecks];
function render(){filt();document.querySelectorAll('#nav button').forEach((b,i)=>b.classList.toggle('on',i==tab));
 $('#view').innerHTML=F.length?views[tab]():'<div class="card">No tasks match.</div>'}
$('#foot').innerHTML=`Generated ${D.generated} from <code>${esc(D.root)}</code> (${D.files} files, ${D.sessions.length} sessions). A <b>task</b> = one human prompt through to the last activity before the next prompt; a <b>turn</b> = one model API call.
 Costs are <b>estimates</b> from token usage × configured $/MTok rates (${esc(JSON.stringify(D.price))}); * = includes models with unknown pricing. Estimates typically land ~90-95% of the CLI's own reported total (advisor/side calls are not in transcripts). Subagent transcripts are attributed to the task running when they started.
 Time split uses interval union (model &gt; tools &gt; subagent &gt; user tools), so parallel work is not double counted; "idle" is time with no model or tool activity.`;
document.addEventListener('click',e=>{const el=e.target.closest('[data-t],[data-s],[data-task]');if(!el)return;
 if(el.dataset.t!=null){tab=+el.dataset.t;render()}else if(el.dataset.s){const[id,i]=el.dataset.s.split('|'),s=sorts[id];s.d=s.i==+i?-s.d:-1;s.i=+i;render();if(cur&&$('#modal').style.display=='block')$('#mbody').innerHTML=detail(cur)}
 else{cur=el.dataset.task;$('#mbody').innerHTML=detail(cur);$('#modal').style.display='block'}});
$('#x').onclick=()=>$('#modal').style.display='none';$('#modal').onclick=e=>{if(e.target.id=='modal')e.target.style.display='none'};
$('#fp').onchange=$('#fq').oninput=render;render();
</script></body></html>
'''


if __name__ == '__main__':
    main()
