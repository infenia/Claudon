import json
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
