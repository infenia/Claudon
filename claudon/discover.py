import collections, datetime as dt, sys
from pathlib import Path

from .analyze import analyze_session
from .pricing import PRICE
from .transcript import loads


def discover(root):
    root = Path(root).expanduser()
    if root.is_file():
        return root.parent, [root]
    base = root / 'projects' if (root / 'projects').is_dir() else root
    # is_file(): skips directories named *.jsonl and broken symlinks
    return base, sorted(p for p in base.rglob('*.jsonl') if 'tool-results' not in p.parts and p.is_file())


def first_session_id(path):
    """sessionId of the first record that has one; stops reading at the first match."""
    try:
        with open(path, encoding='utf-8-sig', errors='replace') as f:
            for line in f:
                if 'sessionId' not in line:
                    continue
                try:
                    r = loads(line)
                except ValueError:
                    continue
                if isinstance(r, dict) and isinstance(r.get('sessionId'), str):
                    return r['sessionId']
    except OSError:
        # unreadable here -> treat as an original session; build() reports the read error when it analyses it
        return None
    return None


def copy_last(item):
    """Sort key: originals before forked/resumed copies, so shared history is credited to the original.
    A copy's leading records carry the source session's id; file mtime only breaks ties."""
    (proj, sid), files = item
    main = [p for p, is_sub in files if not is_sub]
    is_copy = bool(main) and first_session_id(main[0]) not in (None, sid)
    return is_copy, min(p.stat().st_mtime for p, _ in files)


def build(root):
    base, paths = discover(root)
    groups = collections.defaultdict(list)             # (project, session id) -> files
    for p in paths:
        parts = p.relative_to(base).parts
        sub = 'subagents' in parts
        i = parts.index('subagents') if sub else None
        sid = (parts[i - 1] if i else base.name) if sub else p.stem   # i == 0: PATH is the <session>/ dir itself
        depth = parts.index('subagents') - 1 if sub else len(parts) - 1     # dirs above the session
        proj = parts[0] if depth >= 1 else base.name                         # base may itself be one project
        groups[(proj, sid)].append((p, sub))
    sessions, tasks, seen, keys = [], [], set(), set()
    for (proj, sid), files in sorted(groups.items(), key=copy_last):
        key = sid if sid not in keys else f'{sid}@{proj}'    # same session id under two projects: keep task ids unique
        keys.add(key)
        try:
            s, ts = analyze_session(key, proj, sorted(files, key=lambda f: f[1]), seen)
        except Exception as e:                              # one unreadable/malformed session must not sink the report
            print(f'warning: skipped session {sid} in {proj}: {type(e).__name__}: {e}', file=sys.stderr)
            continue
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
