def redact(d):
    names, servers, sids = {}, {}, {}

    def tool(n):                                    # mcp__<server>__<tool>: server names can be internal
        parts = n.split('__') if isinstance(n, str) else []
        if len(parts) < 2 or parts[0] != 'mcp':
            return n
        server, rest = ('__'.join(parts[1:-1]), f'__{parts[-1]}') if len(parts) > 2 else (parts[1], '')
        return f"mcp__{servers.setdefault(server, f'server-{len(servers) + 1}')}{rest}"     # server names may contain '__'

    for t in d['tasks']:
        t['proj'] = names.setdefault(t['proj'], f'project-{len(names) + 1}')
        t['sid'] = sids.setdefault(t['sid'], f'session-{len(sids) + 1}')
        t['id'] = f"{t['sid']}#{t['id'].rsplit('#', 1)[1]}"
        t['prompt'] = f"Task {t['id']}"; t['title'] = ''
        t['slow'] = [[tool(n), dur, '', e] for n, dur, _, e in t['slow']]
        t['dups'] = [[tool(n), '', k] for n, _, k in t['dups']]
        t['churn'] = [['', k] for _, k in t['churn']]               # file paths
        t['tool_stats'] = {tool(k): v for k, v in t['tool_stats'].items()}
        for sg in t['segs']:
            if sg[0] not in ('m', 'ms'):
                sg[3], sg[4] = tool(sg[3]), ''
    for x in d['sessions']:
        x['cwd'] = x['title'] = ''; x['label'] = x['proj'] = names.get(x['label'], '')
        x['id'] = sids.get(x['id'], '')
    d['root'] = '(redacted)'
