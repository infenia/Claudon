import importlib.util
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


class TestNuitkaAndWasm(unittest.TestCase):

    def test_nuitka_build_script(self):
        script_path = ROOT_DIR / "scripts" / "build_nuitka.py"
        self.assertTrue(script_path.exists(), "scripts/build_nuitka.py should exist")

        spec = importlib.util.spec_from_file_location("build_nuitka", script_path)
        build_nuitka = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build_nuitka)

        self.assertTrue(hasattr(build_nuitka, "check_nuitka"))
        self.assertTrue(hasattr(build_nuitka, "build_nuitka"))
        # Verify check_nuitka returns boolean without raising error
        is_nuitka_installed = build_nuitka.check_nuitka()
        self.assertIsInstance(is_nuitka_installed, bool)

    def test_wasm_index_html(self):
        wasm_file = ROOT_DIR / "wasm" / "index.html"
        self.assertTrue(wasm_file.exists(), "wasm/index.html should exist")

        content = wasm_file.read_text(encoding="utf-8")
        self.assertIn("pyodide", content.lower())
        self.assertIn("claudon.py", content)
        self.assertIn("drop-zone", content)
        self.assertIn("report-frame", content)

    def test_github_workflow(self):
        workflow_file = ROOT_DIR / ".github" / "workflows" / "nuitka-build.yml"
        self.assertTrue(workflow_file.exists(), ".github/workflows/nuitka-build.yml should exist")

        content = workflow_file.read_text(encoding="utf-8")
        self.assertIn("Nuitka Build", content)
        self.assertIn("build_nuitka.py", content)
        self.assertIn("'v*'", content)

    def test_release_workflow(self):
        release_file = ROOT_DIR / ".github" / "workflows" / "release.yml"
        self.assertTrue(release_file.exists(), ".github/workflows/release.yml should exist")

        content = release_file.read_text(encoding="utf-8")
        self.assertIn("Publish Semantic Release", content)
        self.assertIn("'v*'", content)
        self.assertIn("Publish to PyPI", content)
        self.assertIn("Publish to npm", content)


if __name__ == "__main__":
    unittest.main()
