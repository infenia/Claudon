import datetime
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# Add root directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from claudon import discover, render

# Chromium may expose its built-in AI globals; tests start without them so the dashboard is the same everywhere
NO_AI = "delete window.LanguageModel; delete window.Summarizer;"
# a scripted Prompt API: availability `AVAIL`, model replies from window.__reply(prompt, options); calls land in window.__calls
MOCK_LM = """
window.__calls = [];
const __session = {
  contextWindow: 6000, contextUsage: 0,
  measureContextUsage: async q => q.length / 4,
  clone: async () => __session, destroy() { __calls.push(['destroy']); },
  prompt: async (q, o) => { __calls.push(['prompt', q, o]); return window.__reply(q, o); },
  append: async m => { __calls.push(['append', m]); },
  addEventListener() {},
  promptStreaming(q, o) {
    __calls.push(['stream', q]);
    return (async function* () { for (const c of window.__chunks(q)) yield c; })();
  },
};
window.LanguageModel = {
  availability: async o => { __calls.push(['availability', o]); return 'AVAIL'; },
  create: async o => { __calls.push(['create', o]); if (window.__beforeCreate) await window.__beforeCreate(o); return __session; },
};
delete window.Summarizer;
"""


def at(sec):
    return (datetime.datetime(2025, 1, 1, 12, tzinfo=datetime.timezone.utc) + datetime.timedelta(seconds=sec)).isoformat()


class Transcript:
    """Builds a synthetic session: prompts, and model turns whose tool calls finish after a given number of seconds."""
    def __init__(self):
        self.recs, self.t, self.n = [], 0, 0

    def prompt(self, text):
        self.t += 60
        self.recs.append({"timestamp": at(self.t), "type": "user", "message": {"content": text}})

    def turn(self, *tools, secs=1):
        """tools: (name, input, failed); all run in parallel for `secs` seconds"""
        self.n += 1
        self.t += 1
        ids = [f"t{self.n}_{i}" for i in range(len(tools))]
        self.recs.append({"timestamp": at(self.t), "type": "assistant", "message": {
            "id": f"m{self.n}", "model": "claude-sonnet-5-5", "usage": {"input_tokens": 100, "output_tokens": 50},
            "content": [{"type": "tool_use", "id": i, "name": n, "input": inp} for i, (n, inp, _) in zip(ids, tools)]}})
        self.t += secs
        self.recs.append({"timestamp": at(self.t), "type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": i, "content": "boom" if e else "ok", "is_error": e} for i, (_, _, e) in zip(ids, tools)]}})

    def report(self, path):
        f = path / "projects" / "proj" / "s.jsonl"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("".join(json.dumps(r) + "\n" for r in self.recs), encoding="utf-8")
        out = path / "findings.html"
        out.write_text(render.render_html(discover.build(str(path / "projects"))), encoding="utf-8")
        return out


@unittest.skipUnless(PLAYWRIGHT_AVAILABLE, "Playwright is not installed")
class TestClaudonUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        self.tmp_path = Path(self.tmp_dir.name)

        # Create mock session files to build report
        session_file = self.tmp_path / "projects" / "my-project" / "session_abc.jsonl"
        session_file.parent.mkdir(parents=True, exist_ok=True)

        sample_records = [
            {
                "timestamp": "2025-01-01T12:00:00Z",
                "type": "user",
                "message": {"content": "Build UI test suite"}
            },
            {
                "timestamp": "2025-01-01T12:00:02Z",
                "type": "assistant",
                "message": {
                    "id": "msg_01",
                    "model": "claude-3-5-sonnet-20241022",
                    "usage": {
                        "input_tokens": 1000,
                        "output_tokens": 500,
                        "output_tokens_details": {"thinking_tokens": 100}
                    },
                    "content": [
                        {"type": "thinking", "thinking": "Let me check files..."},
                        {
                            "type": "tool_use",
                            "id": "tool_01",
                            "name": "Bash",
                            "input": {"command": "ls -l"}
                        }
                    ]
                }
            },
            {
                "timestamp": "2025-01-01T12:00:05Z",
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tool_01",
                            "is_error": False,
                            "content": "file1.txt\nfile2.txt"
                        }
                    ]
                }
            },
            {
                "timestamp": "2025-01-01T12:00:10Z",
                "type": "assistant",
                "message": {
                    "id": "msg_02",
                    "model": "claude-3-5-sonnet-20241022",
                    "usage": {"input_tokens": 1200, "output_tokens": 200},
                    "content": [{"type": "text", "text": "Task finished successfully!"}]
                }
            }
        ]

        with open(session_file, "w", encoding="utf-8") as f:
            for rec in sample_records:
                f.write(json.dumps(rec) + "\n")

        data = discover.build(str(self.tmp_path))
        html_content = render.render_html(data)

        self.report_path = self.tmp_path / "report.html"
        self.report_path.write_text(html_content, encoding="utf-8")

        self.context = self.browser.new_context(viewport={"width": 1280, "height": 800})
        self.context.add_init_script(NO_AI)
        self.page = self.context.new_page()
        self.page.goto(self.report_path.as_uri())

    def tearDown(self):
        self.context.close()

    def test_header_content_and_styles(self):
        """Test header content, background color, font sizes, title, nav, filters."""
        header = self.page.locator("header")
        self.assertTrue(header.is_visible())

        # Header background and border
        header_bg = header.evaluate("el => getComputedStyle(el).backgroundColor")
        self.assertEqual(header_bg, "rgb(255, 255, 255)")  # var(--card) in light mode

        # Title text, color, and size
        h1 = self.page.locator("h1")
        self.assertEqual(h1.text_content().strip(), "Claudon")
        h1_font_size = h1.evaluate("el => getComputedStyle(el).fontSize")
        self.assertEqual(h1_font_size, "16px")

        # Nav buttons
        nav_buttons = self.page.locator("#nav button")
        self.assertEqual(nav_buttons.count(), 5)
        button_labels = [nav_buttons.nth(i).text_content() for i in range(5)]
        self.assertEqual(button_labels, ["Overview", "Tasks", "Tools", "Models & thinking", "Bottlenecks"])

        # Active tab styling
        active_btn = nav_buttons.nth(0)
        self.assertIn("on", active_btn.get_attribute("class"))
        active_bg = active_btn.evaluate("el => getComputedStyle(el).backgroundColor")
        self.assertEqual(active_bg, "rgb(59, 130, 246)")  # var(--model)

        # Dropdown and search box size / presence
        fp = self.page.locator("#fp")
        fq = self.page.locator("#fq")
        self.assertTrue(fp.is_visible())
        self.assertTrue(fq.is_visible())
        self.assertIn("my-project", fp.text_content())

    def test_kpi_cards_content_colors_and_sizes(self):
        """Test KPI cards rendering, text values, colors, font sizes, and box dimensions."""
        kpi_cards = self.page.locator(".grid .card")
        self.assertGreater(kpi_cards.count(), 0)

        first_card = kpi_cards.nth(0)
        card_label = first_card.locator(".k")
        card_val = first_card.locator(".v")
        card_sub = first_card.locator(".s")

        self.assertEqual(card_label.text_content().strip(), "Tasks")
        self.assertEqual(card_val.text_content().strip(), "1")
        self.assertIn("1 sessions", card_sub.text_content())

        # Check font sizes and text transform for .k
        k_font_size = card_label.evaluate("el => getComputedStyle(el).fontSize")
        k_transform = card_label.evaluate("el => getComputedStyle(el).textTransform")
        self.assertEqual(k_font_size, "12px")
        self.assertEqual(k_transform, "uppercase")

        # Check .v font size and font weight
        v_font_size = card_val.evaluate("el => getComputedStyle(el).fontSize")
        v_font_weight = card_val.evaluate("el => getComputedStyle(el).fontWeight")
        self.assertEqual(v_font_size, "24px")
        self.assertEqual(v_font_weight, "600")

        # Check card border and border radius
        border_radius = first_card.evaluate("el => getComputedStyle(el).borderRadius")
        self.assertEqual(border_radius, "10px")

    def test_time_split_bar_and_legend(self):
        """Test wall-clock time split bar colors, heights, and legend indicators."""
        bar = self.page.locator(".bar").first
        self.assertTrue(bar.is_visible())

        # Bar dimensions
        bar_box = bar.bounding_box()
        self.assertIsNotNone(bar_box)
        self.assertEqual(bar_box["height"], 10)
        self.assertGreaterEqual(bar_box["width"], 110)

        # Check bar segment colors matching CSS variables
        m_seg = bar.locator("i.m")
        if m_seg.count() > 0:
            m_bg = m_seg.evaluate("el => getComputedStyle(el).backgroundColor")
            self.assertEqual(m_bg, "rgb(59, 130, 246)")  # --model

        t_seg = bar.locator("i.t")
        if t_seg.count() > 0:
            t_bg = t_seg.evaluate("el => getComputedStyle(el).backgroundColor")
            self.assertEqual(t_bg, "rgb(245, 158, 11)")  # --tool

        # Check legend items size and colors
        legend_squares = self.page.locator(".leg b")
        self.assertEqual(legend_squares.count(), 6)

        first_leg_sq = legend_squares.nth(0)
        leg_box = first_leg_sq.bounding_box()
        self.assertEqual(leg_box["width"], 10)
        self.assertEqual(leg_box["height"], 10)

        leg_m_bg = first_leg_sq.evaluate("el => getComputedStyle(el).backgroundColor")
        self.assertEqual(leg_m_bg, "rgb(59, 130, 246)")

    def test_tables_content_and_styling(self):
        """Test tables rendering, headers, cell padding, and numeric alignment."""
        tables = self.page.locator("table")
        self.assertGreater(tables.count(), 0)

        first_table = tables.nth(0)
        th_elements = first_table.locator("th")
        self.assertGreater(th_elements.count(), 0)

        th_font_size = th_elements.nth(0).evaluate("el => getComputedStyle(el).fontSize")
        self.assertEqual(th_font_size, "12px")

        # Check numeric alignment class 'n'
        numeric_headers = first_table.locator("th.n")
        if numeric_headers.count() > 0:
            num_align = numeric_headers.nth(0).evaluate("el => getComputedStyle(el).textAlign")
            self.assertEqual(num_align, "right")

    def test_navigation_and_tab_views(self):
        """Test switching tabs renders correct sections and contents."""
        nav_buttons = self.page.locator("#nav button")

        # Click Tasks Tab
        nav_buttons.nth(1).click()
        self.assertTrue(self.page.locator("#view table").is_visible())
        task_prompt = self.page.locator(".pr")
        self.assertIn("Build UI test suite", task_prompt.text_content())

        # Click Tools Tab
        nav_buttons.nth(2).click()
        self.assertIn("Tools by total time", self.page.content())
        self.assertIn("Bash", self.page.content())

        # Click Models & thinking Tab
        nav_buttons.nth(3).click()
        self.assertIn("Models", self.page.content())
        self.assertIn("Thinking", self.page.content())

        # Click Bottlenecks Tab
        nav_buttons.nth(4).click()
        self.assertIn("Automatic findings", self.page.content())

    def test_task_modal_detail_popup(self):
        """Test clicking task opens modal with detailed contents, Gantt timeline, and context SVG."""
        # Switch to Tasks tab
        self.page.locator('#nav button[data-t="1"]').click()

        # Click the first task row
        task_row = self.page.locator("tr.c").first
        task_row.click()

        modal = self.page.locator("#modal")
        self.assertTrue(modal.is_visible())

        # Modal body contents
        mbody = self.page.locator("#mbody")
        self.assertIn("Build UI test suite", mbody.text_content())
        self.assertIn("Timeline", mbody.text_content())

        # Gantt chart and lanes
        gantt = mbody.locator(".gantt")
        self.assertTrue(gantt.is_visible())
        lanes = gantt.locator(".lane")
        self.assertEqual(lanes.count(), 3)  # model, tools, subagent

        # Lane height check
        lane_height = lanes.nth(0).evaluate("el => getComputedStyle(el).height")
        self.assertEqual(lane_height, "24px")

        # Close modal
        close_x = self.page.locator("#x")
        close_x.click()
        self.assertFalse(modal.is_visible())

    def test_tables_load_more_rows(self):
        """Tables longer than a page offer 'show N more' / 'show all' instead of silently truncating."""
        recs = []
        for i in range(20):                               # 20 tasks; the thinking table pages by 15
            recs.append({"timestamp": f"2025-01-01T12:{i:02d}:00Z", "type": "user", "message": {"content": f"task {i}"}})
            recs.append({"timestamp": f"2025-01-01T12:{i:02d}:05Z", "type": "assistant",
                         "message": {"id": f"m{i}", "model": "claude-sonnet-5-5", "usage": {"output_tokens": 5}, "content": []}})
        f = self.tmp_path / "many" / "proj" / "s.jsonl"
        f.parent.mkdir(parents=True)
        f.write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
        report = self.tmp_path / "many.html"
        report.write_text(render.render_html(discover.build(str(f))), encoding="utf-8")
        self.page.goto(report.as_uri())
        self.page.click("nav button:text-is('Models & thinking')")
        card = self.page.locator(".card", has=self.page.locator("h2", has_text="Most thinking-heavy tasks"))
        rows = lambda: card.locator("table tr").count() - 1
        self.assertEqual(rows(), 15)
        self.assertIn("showing 15 of 20", card.locator(".more").inner_text())
        card.locator(".more button", has_text="show 5 more").click()
        self.assertEqual(rows(), 20)
        self.assertEqual(card.locator(".more").count(), 0)
        self.page.fill("#fq", "task")                      # a new filter starts again at page 1
        self.assertEqual(rows(), 15)
        card.locator(".more button", has_text="show all").click()
        self.assertEqual(rows(), 20)

    def open_bottlenecks(self, tr):
        self.page.goto(tr.report(self.tmp_path / "f").as_uri())
        self.page.click("nav button:text-is('Bottlenecks')")
        return lambda key: self.page.locator(f"#f-{key}")

    def test_findings_target_the_right_tasks_and_say_how_to_fix(self):
        tr = Transcript()
        tr.prompt("flaky build")
        for i in range(10):
            tr.turn(("Bash", {"command": "make"}, i % 3 == 0))             # 4 of 10 fail
        for _ in range(10):
            tr.turn(("Edit", {"file_path": "/src/app/main.py"}, False))   # churn: 10 edits to one file
        for _ in range(6):
            tr.turn(("Read", {"file_path": "/src/app/util.py"}, False))   # 5 identical repeats
        tr.prompt("approve edits")
        for _ in range(3):
            tr.turn(("Edit", {"file_path": "/src/b.py"}, False), secs=50)  # 150 s waiting on permission prompts
        tr.prompt("clean task")
        tr.turn(*[("Bash", {"command": f"job {i}"}, False) for i in range(3)], secs=30)   # 3 parallel calls
        finding = self.open_bottlenecks(tr)

        errors = finding("tool-errors")
        self.assertIn("Bash: 4/13 failed", errors.inner_text())
        chips = errors.locator(".chip").all_inner_texts()
        self.assertEqual([c.split(" · ")[0] for c in chips], ["flaky build"])     # not tasks without Bash errors
        self.assertIn("Fix:", errors.inner_text())
        self.assertIn("CLAUDE.md", errors.locator(".fix code").all_inner_texts())

        self.assertIn("main.py ×10", finding("churn").inner_text())
        self.assertIn("5 repeated identical", finding("repeats").inner_text())
        approval = finding("approval")
        self.assertIn("2m 30s", approval.inner_text())
        self.assertIn("permissions.allow", approval.inner_text())
        self.assertEqual(approval.locator(".chip").all_inner_texts()[0].split(" · ")[0], "approve edits")

        share = re.search(r"\((\d+)% of summed tool-call time\)", finding("slow-tool").inner_text())
        self.assertLessEqual(int(share.group(1)), 100)   # parallel calls used to push this past 100%

        sev = self.page.locator(".find").evaluate_all("els => els.map(e => e.classList[1])")
        self.assertEqual(sev, sorted(sev, key=["hi", "mid", "info"].index))   # worst first

    def test_finding_chip_opens_task_detail_with_signals(self):
        tr = Transcript()
        tr.prompt("approve edits")
        for _ in range(3):
            tr.turn(("Edit", {"file_path": "/src/b.py"}, False), secs=50)
        finding = self.open_bottlenecks(tr)
        finding("approval").locator(".chip").first.click()
        self.assertIn("Signals: approval waits 2m 30s", self.page.locator("#mbody").inner_text())

    def ai_page(self, avail="available", reply="null", extra=""):
        """Bottlenecks tab of the approval-wait report, with a mocked on-device model"""
        tr = Transcript()
        tr.prompt("approve edits")
        for _ in range(3):
            tr.turn(("Edit", {"file_path": "/src/b.py"}, False), secs=50)
        self.page.add_init_script(MOCK_LM.replace("AVAIL", avail) + f"window.__reply = {reply};" + extra)
        return self.open_bottlenecks(tr)

    SUMMARY = """(q, o) => JSON.stringify({headline: 'Approvals <img src=x onerror="window.__xss=1"> slow you down',
        summary: 'Most of the wait is permission prompts.',
        priorities: [{finding: 'approval', action: 'Add allow rules'}, {finding: 'invented', action: 'nothing'}]})"""

    def test_ai_hidden_without_browser_support(self):
        self.page.click("nav button:text-is('Bottlenecks')")
        self.assertEqual(self.page.locator("#ai").count(), 0)
        self.assertEqual(self.page.locator("#nav button").count(), 5)

    def test_ai_hidden_when_device_cannot_run_the_model(self):
        self.ai_page(avail="unavailable")
        self.assertEqual(self.page.locator("#ai").count(), 0)

    def test_ai_summary_from_prompt_api(self):
        self.ai_page(reply=self.SUMMARY)
        ai = self.page.locator("#ai")
        ai.locator("button", has_text="Summarize with on-device AI").click()
        self.assertIn("slow you down", ai.locator("p b").inner_text())
        self.assertIn('<img src=x', ai.locator("p b").inner_text())        # model output is text, never markup
        self.assertIsNone(self.page.evaluate("window.__xss"))
        links = ai.locator("ol li a")
        self.assertEqual(links.all_inner_texts(), ["Permission prompts held up 2m 30s of work"])   # invented key dropped
        links.first.click()
        self.assertIn("flash", self.page.locator("#f-approval").get_attribute("class"))
        calls = self.page.evaluate("__calls")
        avail = next(c[1] for c in calls if c[0] == "availability")
        self.assertEqual(avail["expectedInputs"], [{"type": "text", "languages": ["en"]}])
        create = next(c[1] for c in calls if c[0] == "create")
        self.assertEqual(create["initialPrompts"][0]["role"], "system")
        prompt = next(c for c in calls if c[0] == "prompt")
        self.assertIn('"key":"approval"', prompt[1])                         # grounded on the findings
        self.assertEqual(prompt[2]["responseConstraint"]["properties"]["priorities"]["items"]["properties"]["finding"]["enum"][0], "approval")

    def test_ai_summary_is_cached_per_report(self):
        self.ai_page(reply=self.SUMMARY)
        self.page.locator("#ai button").click()
        self.page.locator("#ai ol").wait_for()
        self.page.reload()
        self.page.click("nav button:text-is('Bottlenecks')")
        self.assertIn("slow you down", self.page.locator("#ai").inner_text())
        self.assertFalse(any(c[0] == "prompt" for c in self.page.evaluate("__calls")))

    def test_ai_model_download_shows_progress(self):
        gate = """window.__beforeCreate = o => new Promise(go => {
            const m = new EventTarget(); o.monitor(m);
            const e = new Event('downloadprogress'); e.loaded = 0.5; e.total = 1; m.dispatchEvent(e);
            window.__finish = go; });"""
        self.ai_page(avail="downloadable", reply=self.SUMMARY, extra=gate)
        ai = self.page.locator("#ai")
        self.assertIn("downloads its built-in model once", ai.inner_text())
        ai.locator("button", has_text="Enable on-device AI").click()
        self.assertEqual(self.page.locator("#aipcttxt").inner_text(), "50%")
        self.page.evaluate("window.__finish()")
        self.assertIn("slow you down", ai.locator("p b").inner_text())

    def test_ai_failure_keeps_the_dashboard(self):
        self.ai_page(extra="window.__beforeCreate = async () => { throw new DOMException('no GPU', 'NotSupportedError'); };")
        self.page.locator("#ai button").click()
        self.assertIn("The on-device model failed: no GPU", self.page.locator("#ai .aierr").inner_text())
        self.assertTrue(self.page.locator("#f-approval").is_visible())

    def test_ai_summary_from_summarizer_api(self):
        self.page.add_init_script("""delete window.LanguageModel; window.__seen = [];
            window.Summarizer = {availability: async () => 'available', create: async o => ({destroy() {},
              summarizeStreaming: (text, opt) => { __seen.push(text); return (async function* () { yield '* Approve less often.'; yield '\\n* Then fix Bash.'; })(); }})};""")
        tr = Transcript()
        tr.prompt("approve edits")
        for _ in range(3):
            tr.turn(("Edit", {"file_path": "/src/b.py"}, False), secs=50)
        self.open_bottlenecks(tr)
        self.assertIn("Summarizer API", self.page.locator("#ai h2").inner_text())
        self.assertEqual(self.page.locator("#nav button").count(), 5)           # no chat without the Prompt API
        self.page.locator("#ai button").click()
        self.assertEqual(self.page.locator("#aitext").inner_text(), "* Approve less often.\n* Then fix Bash.")
        self.assertIn("Permission prompts held up", self.page.evaluate("__seen[0]"))

    def chat_page(self, chunks):
        """Ask AI tab over two tasks; the mocked model streams chunks(question)"""
        tr = Transcript()
        tr.prompt("cheap task")
        tr.turn(("Read", {"file_path": "/a.py"}, False))
        tr.prompt("costly task")
        for _ in range(12):
            tr.turn(("Bash", {"command": "make"}, False))
        self.page.add_init_script(MOCK_LM.replace("AVAIL", "available") + f"window.__chunks = {chunks};")
        self.page.goto(tr.report(self.tmp_path / "c").as_uri())
        self.page.click("nav button:text-is('Ask AI')")
        return self.page.evaluate("[...D.tasks].sort((x, y) => y.cost - x.cost)[0].id")

    def ask(self, q):
        self.page.fill("#q", q)
        self.page.keyboard.press("Enter")
        self.page.locator("#ask button", has_text="Ask").wait_for()          # Stop turns back into Ask when done

    def test_chat_tab_only_with_prompt_api(self):
        self.chat_page("q => ['ok']")
        self.assertEqual(self.page.locator("#nav button").all_inner_texts()[-1], "Ask AI")
        self.page.set_viewport_size({"width": 390, "height": 800})                 # six tabs scroll inside the nav, not the page
        self.assertLessEqual(self.page.evaluate("document.documentElement.scrollWidth"), 390)

    def test_chat_answers_with_cited_tasks_and_shows_its_data(self):
        costly = self.chat_page("q => ['The most expensive is ', '[' + [...D.tasks].sort((x, y) => y.cost - x.cost)[0].id + ']', ', not [nope#9].']")
        self.ask("Which task cost the most?")
        answer = self.page.locator(".msg.a").last
        self.assertIn("The most expensive is", answer.inner_text())
        self.assertIn("[nope#9]", answer.inner_text())                       # invented ids stay plain text
        chip = answer.locator(".chip")
        self.assertEqual(chip.count(), 1)
        self.assertEqual(chip.get_attribute("data-task"), costly)
        data = json.loads(answer.locator("details pre").text_content())
        self.assertEqual((data["ranked_by"], data["top_tasks"][0]["id"]), ("cost", costly))
        chip.click()
        self.assertIn("costly task", self.page.locator("#mbody").inner_text())
        sent = next(c[1] for c in self.page.evaluate("__calls") if c[0] == "append")
        self.assertIn("Report data for the current view", sent[0]["content"])

    def test_chat_retrieval_follows_the_question(self):
        self.chat_page("q => ['ok']")
        ctx = self.page.evaluate("context('Which tools fail most, and in which tasks?', F)")
        self.assertEqual(ctx["ranked_by"], "tool errors")
        self.assertEqual({t["tool"] for t in ctx["tools"]}, {"Bash", "Read"})
        ctx = self.page.evaluate("context('what happened in ' + D.tasks[0].id + ' ?', F)")
        self.assertEqual(ctx["named_tasks"][0]["prompt"], "cheap task")

    def test_chat_persists_across_reloads_until_cleared(self):
        self.chat_page("q => ['Answer to: ' + q.split('Question: ')[1]]")
        self.page.locator(".chip[data-q]").first.click()                       # a suggested question
        self.page.locator(".msg.a", has_text="Answer to: What should I fix first?").wait_for()
        self.page.reload()
        self.page.click("nav button:text-is('Ask AI')")
        self.assertEqual(self.page.locator(".msg").count(), 2)
        self.ask("And then?")
        history = next(c[1] for c in self.page.evaluate("__calls") if c[0] == "append")
        self.assertEqual([m["role"] for m in history[2:]], ["user", "assistant"])   # earlier turns rebuilt into the session
        self.page.click("[data-chat=clear]")
        self.assertEqual(self.page.locator(".msg").count(), 0)
        self.page.reload()
        self.page.click("nav button:text-is('Ask AI')")
        self.assertEqual(self.page.locator(".msg").count(), 0)

    def test_dark_mode_color_scheme(self):
        """Test theme dark mode CSS variable overrides for background and card colors."""
        dark_context = self.browser.new_context(
            viewport={"width": 1280, "height": 800},
            color_scheme="dark"
        )
        dark_page = dark_context.new_page()
        dark_page.goto(self.report_path.as_uri())

        bg_color = dark_page.locator("body").evaluate("el => getComputedStyle(el).backgroundColor")
        card_color = dark_page.locator(".card").first.evaluate("el => getComputedStyle(el).backgroundColor")

        # In dark mode: --bg is #10131a -> rgb(16, 19, 26), --card is #181c26 -> rgb(24, 28, 38)
        self.assertEqual(bg_color, "rgb(16, 19, 26)")
        self.assertEqual(card_color, "rgb(24, 28, 38)")

        dark_context.close()


if __name__ == "__main__":
    unittest.main()
