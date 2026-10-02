import datetime
import json
import os
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

# Add root directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from claudon import cli, discover, pricing, render, transcript
from claudon.redaction import redact


def user(ts, text):
    return {"timestamp": f"2026-01-01T12:00:{ts:02d}Z", "type": "user", "message": {"content": text}}


def assistant(ts, mid, model="claude-sonnet-5-5", content=()):
    return {"timestamp": f"2026-01-01T12:00:{ts:02d}Z", "type": "assistant",
            "message": {"id": mid, "model": model, "usage": {"input_tokens": 100, "output_tokens": 50},
                        "content": list(content)}}


def at(sec):
    """ISO timestamp `sec` seconds after 2026-01-01T12:00:00Z (the helpers above only reach 59 s)."""
    return (datetime.datetime(2026, 1, 1, 12, tzinfo=datetime.timezone.utc) + datetime.timedelta(seconds=sec)).isoformat()


def call(sec, mid, tools=(), usage=None):
    """assistant record at `sec` issuing tool_use blocks [(id, name, input)]"""
    return {"timestamp": at(sec), "type": "assistant",
            "message": {"id": mid, "model": "claude-sonnet-5-5", "usage": usage or {"input_tokens": 100, "output_tokens": 50},
                        "content": [{"type": "tool_use", "id": i, "name": n, "input": inp} for i, n, inp in tools]}}


def results(sec, *res):
    """user record at `sec` carrying tool_results [(id, is_error)]"""
    return {"timestamp": at(sec), "type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": i, "content": "boom" if e else "ok", "is_error": e} for i, e in res]}}


def strict_json(const):
    raise ValueError(f"{const} is not valid JSON")


class TestClaudon(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        self.tmp_path = Path(self.tmp_dir.name)

    def write(self, rel, lines):
        f = self.tmp_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("".join((x if isinstance(x, str) else json.dumps(x)) + "\n" for x in lines), encoding="utf-8")
        return f

    def test_price_longest_key_wins(self):
        self.assertEqual(pricing.price("claude-opus-5-5")[0][:2], (4, 20))
        self.assertEqual(pricing.price("claude-opus-4-8")[0][:2], (5, 25))
        self.assertEqual(pricing.price("claude-opus-4-1-20250805")[0][:2], (15, 75))
        self.assertEqual(pricing.price("claude-sonnet-4-6")[0][:2], (3, 15))
        self.assertEqual(pricing.price("claude-fable-5-1"), ((10, 50, .25, 12.5, 20), False))
        with mock.patch.dict(pricing.PRICE, {"claude-opus-5-5": (1, 1, 1, 1, 1)}):
            self.assertEqual(pricing.price("claude-opus-5-5")[0], (1, 1, 1, 1, 1))

    def test_load_pricing_validates(self):
        good = self.tmp_path / "p.json"
        good.write_text('{"My-Model": [1, 2, 0.1, 1.25, 2]}', encoding="utf-8")
        self.assertEqual(pricing.load_pricing(good), {"my-model": (1, 2, 0.1, 1.25, 2)})
        bad = self.tmp_path / "bad.json"
        bad.write_text('{"x": [1, 2]}', encoding="utf-8")
        with self.assertRaises(SystemExit):
            pricing.load_pricing(bad)

    def test_malformed_lines_are_skipped(self):
        f = self.write("p/proj/s.jsonl", [user(0, "hi"), "[]", "not json", '{"timestamp": "x"}',
                                          {"type": "user", "message": "str"}, assistant(5, "m1")])
        self.assertEqual(len(discover.build(str(f))["tasks"]), 1)

    def test_synthetic_messages_are_not_api_calls(self):
        f = self.write("p/proj/s.jsonl", [user(0, "hi"), assistant(5, "m1"), assistant(6, "m2", model="<synthetic>")])
        t = discover.build(str(f))["tasks"][0]
        self.assertEqual((t["calls"], t["est"], list(t["models"])), (1, False, ["claude-sonnet-5-5"]))

    def test_task_ids_unique_across_sessions_sharing_prefix(self):
        for name in ("agent-aaaa1111", "agent-aaaa2222"):
            self.write(f"p/proj/{name}.jsonl", [user(0, "hi"), assistant(5, name)])
        ids = [t["id"] for t in discover.build(str(self.tmp_path / "p"))["tasks"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_redact_strips_prompt_and_mcp_server_names(self):
        tool = {"type": "tool_use", "id": "tu1", "name": "mcp__acme-internal__corp__search", "input": {"query": "q"}}
        result = {"timestamp": "2026-01-01T12:00:07Z", "type": "user",
                  "message": {"content": [{"type": "tool_result", "tool_use_id": "tu1", "content": "ok"}]}}
        f = self.write("p/proj/0b5e7c2a-1111.jsonl", [user(0, "secret prompt"), assistant(5, "m1", content=[tool]), result])
        data = discover.build(str(f))
        redact(data)
        dumped = json.dumps(data)
        self.assertNotIn("secret prompt", dumped)
        self.assertNotIn("acme-internal", dumped)
        self.assertNotIn("corp", dumped)
        self.assertIn("mcp__server-1__search", data["tasks"][0]["tool_stats"])
        self.assertNotIn(f.stem, dumped)                  # session ids are replaced too
        self.assertEqual(data["tasks"][0]["id"], "session-1#0")

    def test_price_lookup(self):
        p, est = pricing.price('claude-3-5-sonnet-20241022')
        self.assertEqual(p, pricing.PRICE['sonnet'])
        self.assertFalse(est)

        p_unknown, est_unknown = pricing.price('unknown-model')
        self.assertTrue(est_unknown)

    def test_install_plugin(self):
        fake_home = self.tmp_path / "home"
        with mock.patch.dict(os.environ, {"HOME": str(fake_home), "USERPROFILE": str(fake_home)}):
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
            cli.install_plugin()
        cmd_file = fake_home / ".claude" / "commands" / "claudon.md"
        self.assertTrue(cmd_file.exists())
        self.assertIn("claudon", cmd_file.read_text(encoding="utf-8"))

    def test_install_plugin_keeps_user_edits_unless_forced(self):
        cfg = self.tmp_path / "cfg"
        cmd_file = cfg / "commands" / "claudon.md"
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(cfg)}):
            cli.install_plugin()
            cli.install_plugin()                     # unchanged: no-op
            cmd_file.write_text("my edits", encoding="utf-8")
            with self.assertRaises(SystemExit):
                cli.install_plugin()
            self.assertEqual(cmd_file.read_text(encoding="utf-8"), "my edits")
            cli.install_plugin(force=True)
        self.assertIn("claudon", cmd_file.read_text(encoding="utf-8"))

    def test_call_start_skips_records_written_with_the_response(self):
        prompt = dict(user(0, "hi"), uuid="u1")
        att = {"timestamp": "2026-01-01T12:00:30Z", "type": "attachment", "uuid": "a1", "parentUuid": "u1",
               "attachment": {"type": "deferred_tools_record"}}
        reply = dict(assistant(30, "m1"), uuid="r1", parentUuid="a1")
        t = discover.build(str(self.write("p/proj/s.jsonl", [prompt, att, reply])))["tasks"][0]
        self.assertEqual(t["model_s"], 30)

    def test_user_rejection_is_not_a_tool_error(self):
        uses = [{"type": "tool_use", "id": i, "name": "Bash", "input": {}} for i in ("t1", "t2", "t3")]
        res = lambda i, text, err: {"type": "tool_result", "tool_use_id": i, "content": text, "is_error": err}
        f = self.write("p/proj/s.jsonl", [
            user(0, "hi"), assistant(5, "m1", content=uses),
            {"timestamp": "2026-01-01T12:00:09Z", "type": "user", "message": {"content": [
                res("t1", "The user doesn't want to proceed with this tool use.", True),
                res("t2", "command not found", True),
                res("t3", "log: job interrupted at 12:00", False)]}}])
        n, err, _, _, stopped, done = discover.build(str(f))["tasks"][0]["tool_stats"]["Bash"]
        self.assertEqual((n, err, stopped, done), (3, 1, 1, 3))

    def test_approval_wait_on_instant_tools(self):
        f = self.write("p/proj/s.jsonl", [
            user(0, "hi"), call(1, "m1", [("e1", "Edit", {"file_path": "a.py"}), ("r1", "Read", {"file_path": "a.py"})]),
            results(41, ("e1", False)), results(42, ("r1", False)),       # 40 s on Edit = a permission prompt
            call(43, "m2", [("b1", "Bash", {"command": "sleep 30"})]), results(80, ("b1", False))])  # slow Bash is real work
        self.assertEqual(discover.build(str(f))["tasks"][0]["approval_s"], 81)

    def test_cache_miss_after_idle_gap(self):
        warm = {"input_tokens": 10, "output_tokens": 10, "cache_read_input_tokens": 50000, "cache_creation_input_tokens": 1000}
        cold = {"input_tokens": 10, "output_tokens": 10, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 51000}
        f = self.write("p/proj/s.jsonl", [user(0, "hi"), call(5, "m1", usage=warm), call(20, "m2", usage=warm),
                                          call(400, "m3", usage=cold)])      # 6 min later: the 5 min cache expired
        n, tokens, usd = discover.build(str(f))["tasks"][0]["cache_miss"]
        self.assertEqual((n, tokens), (1, 51000))
        self.assertAlmostEqual(usd, 51000 * 2 * 1.25 / 1e6)

    def test_compaction_shrink_is_not_a_cache_miss(self):
        big = {"input_tokens": 10, "output_tokens": 10, "cache_read_input_tokens": 50000}
        small = {"input_tokens": 10, "output_tokens": 10, "cache_creation_input_tokens": 5000}
        f = self.write("p/proj/s.jsonl", [user(0, "hi"), call(5, "m1", usage=big), call(400, "m2", usage=small)])
        self.assertEqual(discover.build(str(f))["tasks"][0]["cache_miss"], [0, 0, 0])

    def test_repeated_calls_edit_churn_and_error_streak(self):
        recs, n = [user(0, "hi")], 0
        def tool(name, inp, err=False):
            nonlocal n
            n += 1
            recs.extend([call(n * 2, f"m{n}", [(f"t{n}", name, inp)]), results(n * 2 + 1, (f"t{n}", err))])
        for _ in range(3):
            tool("Read", {"file_path": "a.py"})                         # same read three times: 2 repeats
        tool("Read", {"file_path": "a.py", "offset": 200})              # paging further is not a repeat
        for _ in range(4):
            tool("Edit", {"file_path": "a.py", "old_string": "x", "new_string": "y"})
        for _ in range(3):
            tool("Bash", {"command": "make"}, err=True)
        tool("Bash", {"command": "make"})
        t = discover.build(str(self.write("p/proj/s.jsonl", recs)))["tasks"][0]
        self.assertEqual((t["dup_calls"], t["dups"]), (2, [["Read", "a.py", 3]]))
        self.assertEqual(t["churn"], [["a.py", 4]])
        self.assertEqual(t["err_streak"], 3)
        redact(t_data := {"tasks": [t], "sessions": []})
        self.assertEqual((t_data["tasks"][0]["dups"], t_data["tasks"][0]["churn"]), ([["Read", "", 3]], [["", 4]]))

    def test_user_interrupts_are_counted(self):
        stop = {"timestamp": at(8), "type": "user", "message": {"content": [{"type": "text", "text": "[Request interrupted by user]"}]}}
        f = self.write("p/proj/s.jsonl", [user(0, "hi"), call(5, "m1"), stop, call(9, "m2")])
        t = discover.build(str(f))["tasks"]
        self.assertEqual((len(t), t[0]["interrupts"]), (1, 1))      # an interrupt is not a new task

    def test_cost_mix_sums_to_cost(self):
        a = assistant(5, "m1", model="claude-opus-5-5")
        a["message"]["usage"] = {"input_tokens": 1000, "output_tokens": 500, "cache_read_input_tokens": 20000,
                                 "cache_creation_input_tokens": 3000,
                                 "cache_creation": {"ephemeral_1h_input_tokens": 2000, "ephemeral_5m_input_tokens": 1000}}
        t = discover.build(str(self.write("p/proj/s.jsonl", [user(0, "hi"), a])))["tasks"][0]
        self.assertEqual(t["cost_mix"], [0.004, 0.01, 0.004, 0.021])   # 1h writes at 2x, 5m at 1.25x input
        self.assertAlmostEqual(sum(t["cost_mix"]), t["cost"], places=5)

    def test_subagents_stay_with_session_when_path_is_one_project(self):
        sid = "0b5e7c2a-1111"
        self.write(f"projects/proj-x/{sid}.jsonl", [user(0, "hi"), assistant(5, "m1")])
        self.write(f"projects/proj-x/{sid}/subagents/agent-1.jsonl", [dict(assistant(2, "s1"), isSidechain=True)])
        for path in ("projects", "projects/proj-x"):
            tasks = discover.build(str(self.tmp_path / path))["tasks"]
            self.assertEqual([(t["calls"], t["sub_calls"]) for t in tasks], [(1, 1)], path)

    def test_advisor_iterations_are_priced_on_their_own_row(self):
        a = assistant(5, "m1", model="claude-sonnet-5-5")
        a["message"]["usage"] = {"input_tokens": 100, "output_tokens": 50, "iterations": [
            {"type": "message", "input_tokens": 100, "output_tokens": 50},
            {"type": "advisor_message", "model": "claude-opus-5-5", "input_tokens": 1000, "output_tokens": 200}]}
        t = discover.build(str(self.write("p/proj/s.jsonl", [user(0, "hi"), a])))["tasks"][0]
        executor, advisor = (100 * 2 + 50 * 10) / 1e6, (1000 * 4 + 200 * 20) / 1e6
        self.assertAlmostEqual(t["cost"], executor + advisor)
        self.assertAlmostEqual(t["models"]["claude-opus-5-5 (advisor)"][1], advisor)
        self.assertAlmostEqual(t["models"]["claude-sonnet-5-5"][1], executor)
        self.assertEqual((t["calls"], t["out_tok"]), (1, 250))

    def test_fast_mode_doubles_price(self):
        a = assistant(5, "m1", model="claude-opus-5-5")
        a["message"]["usage"] = {"input_tokens": 1000, "output_tokens": 100, "speed": "fast"}
        t = discover.build(str(self.write("p/proj/s.jsonl", [user(0, "hi"), a])))["tasks"][0]
        self.assertAlmostEqual(t["cost"], (1000 * 8 + 100 * 40) / 1e6)
        self.assertFalse(t["est"])

    def test_slash_commands(self):
        cmd = lambda name, args="": user(0, f"<command-message>{name}</command-message>\n<command-name>/{name}</command-name>"
                                            + (f"\n<command-args>{args}</command-args>" if args else ""))
        self.assertIsNone(transcript.prompt_text(cmd("plugin")))         # local-only, any tag order
        self.assertEqual(transcript.prompt_text(cmd("review", " PR 12 ")), "/review PR 12")
        self.assertEqual(transcript.prompt_text(cmd("init")), "/init")

    def test_hostile_inputs(self):
        cases = {
            "bom": ("\ufeff" + json.dumps(user(0, "real prompt")), "real prompt"),
            "nan record dropped": ('{"type":"cost-state","totalCostUSD":Infinity}', "hi"),
            "quoted command markup": (json.dumps(user(0, "explain <command-name>/clear</command-name> please")),
                                      "explain <command-name>/clear</command-name> please"),
        }
        for name, (first, prompt) in cases.items():
            with self.subTest(name):
                lines = [first] + ([] if name != "nan record dropped" else [user(0, "hi")]) + [assistant(5, "m1")]
                data = discover.build(str(self.write(f"{name}/proj/s.jsonl", lines)))
                self.assertEqual(data["tasks"][0]["prompt"], prompt)
                html = render.render_html(data)
                payload = html.split('<script id="d" type="application/json">', 1)[1].split("</script>", 1)[0]
                json.loads(payload, parse_constant=strict_json)    # browsers' JSON.parse rejects NaN/Infinity

    def test_bad_numbers_and_single_record_tasks(self):
        a = assistant(5, "m1"); a["message"]["usage"] = {"input_tokens": -10**6, "output_tokens": "5"}
        t = discover.build(str(self.write("p/proj/s.jsonl", [user(5, "hi"), a])))["tasks"][0]
        self.assertEqual(t["cost"], 0)
        self.assertGreater(t["wall"], 0)

    def test_unreadable_session_is_skipped_not_fatal(self):
        self.write("p/proj/good.jsonl", [user(0, "hi"), assistant(5, "m1")])
        (self.tmp_path / "p/proj/dir.jsonl").mkdir()
        self.write("p/proj/bad.jsonl", [user(0, "x"), assistant(5, "m2")])
        real = discover.analyze_session
        def flaky(sid, *a):
            if sid == "bad":
                raise OSError("Permission denied")
            return real(sid, *a)
        with mock.patch.object(discover, "analyze_session", flaky), mock.patch("sys.stderr"):
            tasks = discover.build(str(self.tmp_path / "p"))["tasks"]
        self.assertEqual([t["sid"] for t in tasks], ["good"])

    def test_same_session_id_in_two_projects_gets_distinct_task_ids(self):
        for proj in ("projA", "projB"):
            self.write(f"p/{proj}/s1.jsonl", [user(0, proj), assistant(5, f"m-{proj}")])
        ids = [t["id"] for t in discover.build(str(self.tmp_path / "p"))["tasks"]]
        self.assertEqual(len(set(ids)), 2)

    def test_shared_history_credited_to_original_not_copy(self):
        orig = "11111111-aaaa"
        copied = [dict(user(0, "hi"), sessionId=orig), dict(assistant(5, "shared"), sessionId=orig)]
        self.write(f"p/proj/{orig}.jsonl", copied)
        copy = self.write("p/proj/22222222-bbbb.jsonl",
                          copied + [dict(user(10, "new"), sessionId="22222222-bbbb"), dict(assistant(15, "own"), sessionId="22222222-bbbb")])
        os.utime(copy, (0, 0))                           # copy looks older, as after cp or a browser upload
        calls = {t["sid"]: t["calls"] for t in discover.build(str(self.tmp_path / "p"))["tasks"]}
        self.assertEqual(calls, {orig: 1, "22222222-bbbb": 1})

    def test_install_plugin_honours_claude_config_dir(self):
        cfg = self.tmp_path / "cfg"
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(cfg)}):
            cli.install_plugin()
        self.assertTrue((cfg / "commands" / "claudon.md").exists())

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

        data = discover.build(str(session_file))
        self.assertIn("tasks", data)
        self.assertGreater(len(data["tasks"]), 0)

        # Test redact
        redact(data)
        self.assertEqual(data["root"], "(redacted)")

    def test_render_html_escapes_script_close(self):
        data = {"tasks": [{"prompt": "fix </script><img src=x onerror=alert(1)>"}]}
        html = render.render_html(data)
        payload = html.split('<script id="d" type="application/json">', 1)[1].split("</script>", 1)[0]
        self.assertEqual(json.loads(payload), data)

    def test_report_never_navigates_itself(self):
        # opened from file://, Chrome blocks and logs any load of the page's own URL: no forms, no links
        self.assertNotIn("<form", render.TEMPLATE)
        self.assertNotIn("<a ", render.TEMPLATE)
        self.assertNotIn("location.", render.TEMPLATE)

    def test_infenia_attribution_in_template(self):
        self.assertIn("Infenia Private Limited", render.TEMPLATE)
        self.assertIn("MIT License", render.TEMPLATE)


if __name__ == "__main__":
    unittest.main()
