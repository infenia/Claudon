"""Pins build()/redact() output on a synthetic transcript so refactors can't silently change the report data.
Regenerate after an intentional change:  python tests/test_golden.py --update"""
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from claudon import discover
from claudon.redaction import redact

GOLDEN = HERE / 'golden.json'


def snapshot():
    data = discover.build(HERE / 'fixtures')
    out = {'raw': {k: v for k, v in data.items() if k not in ('generated', 'root')}}
    redact(data)
    out['redacted'] = {k: v for k, v in data.items() if k not in ('generated', 'root')}
    return json.loads(json.dumps(out))      # tuples -> lists, as the report sees them


class TestGolden(unittest.TestCase):
    def test_build_matches_golden(self):
        self.assertEqual(snapshot(), json.loads(GOLDEN.read_text(encoding='utf-8')))


if __name__ == '__main__':
    if sys.argv[1:] == ['--update']:
        GOLDEN.write_text(json.dumps(snapshot(), indent=1, sort_keys=True) + '\n', encoding='utf-8')
    else:
        unittest.main()
