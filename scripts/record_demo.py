"""Record docs/assets/demo-{light,dark}.webp from a --redact'ed report (needs playwright + ffmpeg).

    python -m claudon ~/.claude -o /tmp/r.html --redact
    python scripts/record_demo.py /tmp/r.html
"""
import subprocess, sys, tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright

# Fade/slide new content in on every tab switch and modal open (recording only; the dashboard is untouched).
FX = """@keyframes in{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
#view>*{animation:in .45s ease-out}#modal>div{animation:in .35s ease-out}"""
report, out = Path(sys.argv[1]).resolve(), Path(__file__).parent.parent / "docs/assets"
with sync_playwright() as p, tempfile.TemporaryDirectory() as tmp:
    b = p.chromium.launch()
    for scheme in ("light", "dark"):
        ctx = b.new_context(viewport={"width": 1100, "height": 680}, color_scheme=scheme,
                            record_video_dir=tmp, record_video_size={"width": 1100, "height": 680})
        pg = ctx.new_page()
        pg.goto(report.as_uri()); pg.add_style_tag(content=FX); pg.wait_for_timeout(1500)
        pg.mouse.wheel(0, 500); pg.wait_for_timeout(1200); pg.mouse.wheel(0, -500)
        nav = pg.locator("#nav button")
        nav.nth(1).click(); pg.wait_for_timeout(1200)  # Tasks
        pg.locator("tr[data-task]").first.click(); pg.wait_for_timeout(2500)
        pg.keyboard.press("Escape"); pg.wait_for_timeout(400)
        for i in range(2, nav.count()):
            nav.nth(i).click(); pg.wait_for_timeout(1500)
        video = pg.video.path(); ctx.close()
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "0.6", "-i", video, "-vf", "fps=12,scale=960:-1:flags=lanczos",
                        "-loop", "0", "-quality", "50", "-compression_level", "6", out / f"demo-{scheme}.webp"], check=True)
    b.close()
