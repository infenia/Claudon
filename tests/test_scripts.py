import importlib.util
import re
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import claudon


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT_DIR / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestScripts(unittest.TestCase):

    def test_check_nuitka_returns_bool(self):
        self.assertIsInstance(load_script("build_nuitka").check_nuitka(), bool)

    def test_versions_consistent(self):
        check_version = load_script("check_version")
        self.assertEqual(check_version.check(), [])
        self.assertEqual(check_version.check(f"v{claudon.__version__}"), [])
        self.assertTrue(check_version.check("v999.0.0"))

    def test_version_format_valid_for_pypi_and_npm(self):
        ok = load_script("check_version").VERSION_RE.fullmatch
        for v in ("1.2.3", "0.2.0-beta.1", "1.0.0-rc.2"):
            self.assertTrue(ok(v), v)
        for v in ("0.2.0b1", "1.2", "1.0.0-beta"):
            self.assertFalse(ok(v), v)

    def test_wasm_page_only_calls_existing_claudon_api(self):
        page = (ROOT_DIR / "wasm" / "index.html").read_text(encoding="utf-8")
        names = set(re.findall(r"\bclaudon\.([A-Za-z_]\w*)\(", page))
        self.assertTrue(names)
        for name in names:
            self.assertTrue(callable(getattr(claudon, name, None)), name)


if __name__ == "__main__":
    unittest.main()
