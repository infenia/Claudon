import sys
from pathlib import Path

from .transcript import loads

# $/MTok: input, output, cache_read, cache_write_5m, cache_write_1h (Anthropic list prices, 2026-09).
# Keys are model-id substrings; the longest matching key wins, so a bare family name is the
# fallback for its generations. Override or extend with --pricing.
PRICE = {
    'haiku': (1, 5, .1, 1.25, 2),                   # Haiku 4.5
    '3-5-haiku': (.8, 4, .08, 1, 1.6),
    '3-haiku': (.25, 1.25, .03, .3, .5),
    'sonnet': (3, 15, .3, 3.75, 6),                 # Sonnet 3.x / 4.x
    'sonnet-5': (2, 10, .2, 2.5, 4),                # Sonnet 5, 5.5
    'opus': (5, 25, .5, 6.25, 10),                  # Opus 4.5 - 4.8, 5
    'opus-4-0': (15, 75, 1.5, 18.75, 30), 'opus-4-20': (15, 75, 1.5, 18.75, 30),
    'opus-4-1': (15, 75, 1.5, 18.75, 30), '3-opus': (15, 75, 1.5, 18.75, 30),
    'opus-5-5': (4, 20, .2, 5, 8),
    'fable': (10, 50, 1, 12.5, 20), 'mythos': (10, 50, 1, 12.5, 20),    # Fable / Mythos 5
    'fable-5-1': (10, 50, .25, 12.5, 20), 'mythos-5-1': (10, 50, .25, 12.5, 20),
}


def price(model):
    m = (model or '').lower()
    key = max((k for k in PRICE if k in m), key=len, default=None)
    return (PRICE[key], False) if key else ((0, 0, 0, 0, 0), True)      # unknown: flagged as estimate


def cost_mix(u, model):
    """-> ((fresh_in, out, cache_read, cache_write) in $, is_estimate)"""
    p, est = price(model)
    if u.get('fast'):                               # fast mode: 2x list price (documented for Opus 5 / 5.5)
        p, est = tuple(2 * x for x in p), est or 'opus-5' not in (model or '').lower()
    return (u['i'] * p[0] / 1e6, u['o'] * p[1] / 1e6, u['cr'] * p[2] / 1e6, (u['c5'] * p[3] + u['c1'] * p[4]) / 1e6), est


def load_pricing(path):
    """--pricing file: {"model-substring": [in, out, cache_read, write_5m, write_1h]} in $/MTok."""
    try:
        raw = loads(Path(path).read_text(encoding='utf-8-sig'))
        if not isinstance(raw, dict):
            raise ValueError('expected a JSON object')
        out = {}
        for k, v in raw.items():
            if not (isinstance(v, list) and len(v) == 5
                    and all(isinstance(x, (int, float)) and not isinstance(x, bool) and 0 <= x < 1e6 for x in v)):
                raise ValueError(f'{k!r}: expected a list of 5 prices, each a number from 0 to 1e6 $/MTok')
            out[k.lower()] = tuple(v)
        return out
    except (OSError, ValueError) as e:
        sys.exit(f'--pricing {path}: {e}')
