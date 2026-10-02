import bisect, collections, re

from .pricing import cost_mix
from .transcript import load, num, prompt_text, ts_of, usage_of

AGENT_TOOLS = {'Task', 'Agent'}
USER_TOOLS = {'AskUserQuestion', 'ExitPlanMode'}
# how Claude Code marks a tool call the user rejected or interrupted (a user decision, not a tool failure)
USER_STOP = re.compile(r"doesn't want to proceed|tool use was rejected|\[Request interrupted by user", re.I)
MAX_SEGS = 1200
IDLE_SPLIT = 1800                                # seconds of silence that ends a task


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


def tok_sum(calls, k):
    """token total over calls, advisor sub-calls included"""
    return sum(c['u'][k] + sum(au[k] for _, au, _ in c['adv']) for c in calls)


def split(wall, u_m, u_t, u_a, u_u):
    """Rounded time split whose parts never sum past the rounded wall time."""
    parts = dict(model_s=round(u_m, 2), tool_s=round(u_t - u_m, 2), agent_s=round(u_a - u_t, 2), user_s=round(u_u - u_a, 2))
    busy = round(sum(parts.values()), 2)
    w = max(round(wall, 2), busy)
    return dict(wall=w, wait_s=round(w - busy, 2), **parts)


# Row layouts. The dashboard JS reads these arrays by index, so the order is part of the report format.
M_CALLS, M_COST, M_OUT, M_THINK_TOK, M_DUR, M_THINK_S, M_IN, M_CR, M_CC = range(9)     # models[name]
T_N, T_ERR, T_SUM, T_MAX, T_INT = range(5)                                              # tool_stats[name]


def _load_records(files):
    """files: [(path, is_sub)] -> all records, stamped with `_sub` (subagent/sidechain) and `_ts`."""
    recs = []
    for p, is_sub in files:
        for r in load(p):
            r['_sub'] = is_sub or bool(r.get('isSidechain'))
            r['_ts'] = ts_of(r)
            recs.append(r)
    return recs


def _tool_results(recs):
    """tool_use id -> (result timestamp, failed, stopped by the user)"""
    results = {}
    for r in recs:
        c = (r.get('message') or {}).get('content')
        if r['type'] == 'user' and isinstance(c, list) and r['_ts']:
            for b in c:
                if isinstance(b, dict) and b.get('type') == 'tool_result' and isinstance(b.get('tool_use_id'), str):
                    stopped = bool(b.get('is_error')) and bool(USER_STOP.search(str(b.get('content'))[:300]))
                    results[b.get('tool_use_id')] = (r['_ts'], bool(b.get('is_error')) and not stopped, stopped)
    return results


def _build_calls(recs, seen_msgs):
    """API calls (assistant records are streamed one content block per record); adds their ids to seen_msgs."""
    uuid_ts = {r['uuid']: r['_ts'] for r in recs if r.get('uuid') and r['_ts']}
    parent_of = {r['uuid']: r.get('parentUuid') for r in recs if r.get('uuid')}
    by_msg = collections.OrderedDict()
    for r in recs:
        if r['type'] == 'assistant' and r['_ts'] and isinstance(r['message'].get('id'), str) and r['message'].get('model') != '<synthetic>':
            by_msg.setdefault(r['message']['id'], []).append(r)
    calls = []
    for mid, rs in by_msg.items():
        if mid in seen_msgs:                            # forked/resumed sessions copy history
            continue
        rs.sort(key=lambda r: r['_ts'])
        first = rs[0]
        # request start = the parent record, skipping parents stamped as the response arrived
        # (e.g. `deferred_tools_record` attachments), which would zero out the call's duration
        start, u = None, first.get('parentUuid')
        for _ in range(10):
            t = uuid_ts.get(u)
            if t is None or t < first['_ts'] - 0.05:
                start = t
                break
            u = parent_of.get(u)
        start = min(start or first['_ts'], first['_ts'])
        prev, think_s, tools = start, 0.0, []
        for r in rs:
            blocks = r['message'].get('content') if isinstance(r['message'].get('content'), list) else []
            if any(b.get('type') == 'thinking' for b in blocks if isinstance(b, dict)):
                think_s += r['_ts'] - prev
            prev = r['_ts']
            for b in blocks:
                if isinstance(b, dict) and b.get('type') == 'tool_use':
                    tid, name = b.get('id'), b.get('name')
                    tools.append(dict(id=tid if isinstance(tid, str) else None, name=name if isinstance(name, str) and name else '?',
                                      ts=r['_ts'], desc=tool_desc(b.get('input'))))
        u = usage_of(rs)
        model = rs[0]['message'].get('model')
        model = model if isinstance(model, str) else None
        mix, est = cost_mix(u, model)
        adv = []
        for am, au in u['adv']:
            amix, aest = cost_mix(au, am)
            adv.append((am, au, sum(amix)))
            mix, est = tuple(a + b for a, b in zip(mix, amix)), est or aest
        calls.append(dict(adv=adv, mid=mid, start=start, end=rs[-1]['_ts'], think_s=think_s, model=model or '?', u=u, cost=sum(mix), mix=mix,
                          est=est, sub=first['_sub'], tools=tools, eff=first.get('effort'),
                          ctx=u['i'] + u['cr'] + u['c5'] + u['c1']))
    seen_msgs.update(c['mid'] for c in calls)
    return calls


def _task_starts(recs, calls):
    """Tasks = human prompts in the main transcript, plus resumed activity after a long idle gap. -> sorted [(ts, text)]"""
    prompts = [(r['_ts'], t) for r in recs if not r['_sub'] and r['_ts'] and (t := prompt_text(r))]
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
    return prompts


def _bucket(recs, calls, prompts):
    """Assign calls, record timestamps and compactions to the task whose prompt most recently started."""
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
            m = m if isinstance(m, dict) else {}
            T[idx(r['_ts'])]['compacts'].append((r['_ts'], num(m.get('durationMs')) / 1000, num(m.get('preTokens')), num(m.get('postTokens'))))
    return T


def _summarise_task(n, t, sid, proj, title, results):
    """One task bucket -> the task dict the dashboard renders (time split, tokens, cost, models, tools, timeline)."""
    cs = t['calls']
    t0, t1 = t['start'], max(max(t['ends']), max(c['end'] for c in cs))
    wall = max(t1 - t0, 0.01)                       # stays > 0 after round(wall, 2)
    clip = lambda a, b: (max(a, t0), min(b, t1))
    mi, ti, ai, ui, tool_stats, tcalls, segs = [], [], [], [], {}, [], []
    for c in cs:
        mi.append(clip(c['start'], c['end']))
        segs.append(['ms' if c['sub'] else 'm', round(c['start'] - t0, 2), round(c['end'] - c['start'], 2),
                     c['model'], round(c['think_s'], 2), c['u']['o']])
        for tu in c['tools']:
            res = results.get(tu['id'])
            st = tool_stats.setdefault(tu['name'], [0, 0, 0.0, 0.0, 0])
            st[T_N] += 1
            if not res:
                continue
            d = max(0.0, res[0] - tu['ts'])
            st[T_ERR] += res[1]; st[T_SUM] += d; st[T_MAX] = max(st[T_MAX], d); st[T_INT] += res[2]
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
        m = models.setdefault(c['model'], [0, 0.0, 0, 0, 0.0, 0.0, 0, 0, 0])
        m[M_CALLS] += 1; m[M_COST] += c['cost']; m[M_OUT] += c['u']['o']; m[M_THINK_TOK] += c['u']['think']; m[M_DUR] += c['end'] - c['start']
        m[M_THINK_S] += c['think_s']; m[M_IN] += c['u']['i']; m[M_CR] += c['u']['cr']; m[M_CC] += c['u']['c5'] + c['u']['c1']
        m[M_COST] -= sum(x[2] for x in c['adv'])                # advisor share is booked on its own row
        for am, au, acost in c['adv']:
            a = models.setdefault(f'{am} (advisor)', [0, 0.0, 0, 0, 0.0, 0.0, 0, 0, 0])
            a[M_CALLS] += 1; a[M_COST] += acost; a[M_OUT] += au['o']; a[M_IN] += au['i']; a[M_CR] += au['cr']; a[M_CC] += au['c5'] + au['c1']
    if len(segs) > MAX_SEGS:
        segs = sorted(sorted(segs, key=lambda s: -s[2])[:MAX_SEGS], key=lambda s: s[1])
    ctx = [[round(c['start'] - t0, 1), c['ctx']] for c in sorted(main, key=lambda c: c['start'])]
    if len(ctx) > 200:
        ctx = ctx[::len(ctx) // 200 + 1]
    tcalls.sort(key=lambda x: -x[1])
    return dict(
        id=f'{sid}#{n}', sid=sid, proj=proj, title=title, prompt=t['prompt'][:600], start=t0, **split(wall, u_m, u_t, u_a, u_u),
        calls=len(main), sub_calls=len(cs) - len(main), tools=sum(len(c['tools']) for c in cs),
        think_calls=sum(1 for c in cs if c['think_s'] > 0), think_s=round(sum(c['think_s'] for c in cs), 2),
        think_tok=sum(c['u']['think'] for c in cs), out_tok=tok_sum(cs, 'o'),
        in_tok=tok_sum(cs, 'i'), cr_tok=tok_sum(cs, 'cr'), cc_tok=tok_sum(cs, 'c5') + tok_sum(cs, 'c1'),
        cost=round(sum(c['cost'] for c in cs), 5), cost_mix=[round(sum(c['mix'][i] for c in cs), 5) for i in range(4)],
        sub_cost=round(sum(c['cost'] for c in cs if c['sub']), 5),
        est=any(c['est'] for c in cs), ctx_max=max(c['ctx'] for c in cs), compacts=[[round(ct - t0, 1), dur, pre, post] for ct, dur, pre, post in t['compacts']],
        models=models, tool_stats=tool_stats, slow=tcalls, segs=segs, ctx=ctx,
        efforts=sorted({str(c['eff']) for c in cs if c['eff']}))


def analyze_session(sid, proj, files, seen_msgs):
    """files: [(path, is_sub)]. Returns (session dict, [task dicts])."""
    recs = _load_records(files)
    calls = _build_calls(recs, seen_msgs)
    prompts = _task_starts(recs, calls)
    if not prompts:
        return None, []
    title = ''
    for r in recs:
        if r['type'] in ('ai-title', 'custom-title'):
            title = r.get('aiTitle') or r.get('customTitle') or title
    cwd = next((r['cwd'] for r in recs if isinstance(r.get('cwd'), str) and r['cwd']), '')
    reported = max((num(r.get('totalCostUSD')) for r in recs if r['type'] == 'cost-state'), default=0)
    results = _tool_results(recs)
    tasks = [_summarise_task(n, t, sid, proj, title, results) for n, t in enumerate(_bucket(recs, calls, prompts)) if t['calls']]
    if not tasks:
        return None, []
    sess = dict(id=sid, proj=proj, cwd=cwd, title=title, start=min(t['start'] for t in tasks),
                end=max(t['start'] + t['wall'] for t in tasks), tasks=len(tasks), reported_cost=round(reported, 4),
                est_cost=round(sum(t['cost'] for t in tasks), 4))
    return sess, tasks
