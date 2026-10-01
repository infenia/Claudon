import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add root directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import claudon


class TestClaudon(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        self.tmp_path = Path(self.tmp_dir.name)

    def test_price_lookup(self):
        p, est = claudon.price('claude-3-5-sonnet-20241022')
        self.assertEqual(p, claudon.PRICE['sonnet'])
        self.assertFalse(est)

        p_unknown, est_unknown = claudon.price('unknown-model')
        self.assertTrue(est_unknown)

    def test_install_plugin(self):
        fake_home = self.tmp_path / "home"
        orig_home = os.environ.get("HOME")
        os.environ["HOME"] = str(fake_home)
        try:
            claudon.install_plugin()
            cmd_file = fake_home / ".claude" / "commands" / "claudon.md"
            self.assertTrue(cmd_file.exists())
            self.assertIn("claudon", cmd_file.read_text(encoding="utf-8"))
        finally:
            if orig_home is not None:
                os.environ["HOME"] = orig_home
            else:
                os.environ.pop("HOME", None)

    def test_build_and_redact(self):
        # Create a mock session .jsonl file with valid prompt & assistant record
        session_file = self.tmp_path / "session_123.jsonl"
        sample_records = [
            {
                "timestamp": "2025-01-01T12:00:00Z",
                "type": "user",
                "message": {"content": "Help me build a feature"}
            },
            {
                "timestamp": "2025-01-01T12:00:05Z",
                "type": "assistant",
                "message": {
                    "id": "msg_01",
                    "model": "claude-3-5-sonnet-20241022",
                    "usage": {"input_tokens": 100, "output_tokens": 50},
                    "content": [{"type": "text", "text": "I will inspect files."}]
                }
            }
        ]
        with open(session_file, "w", encoding="utf-8") as f:
            for rec in sample_records:
                f.write(json.dumps(rec) + "\n")

        data = claudon.build(str(session_file))
        self.assertIn("tasks", data)
        self.assertGreater(len(data["tasks"]), 0)

        # Test redact
        claudon.redact(data)
        self.assertEqual(data["root"], "(redacted)")

    def test_infenia_attribution_in_template(self):
        self.assertIn("Infenia Private Limited", claudon.TEMPLATE)
        self.assertIn("MIT License", claudon.TEMPLATE)


if __name__ == "__main__":
    unittest.main()
