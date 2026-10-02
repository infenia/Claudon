"""Record docs/assets/demo-{light,dark}.webp + demo-dark.mp4 (Pages site) from a --redact'ed report (needs playwright + ffmpeg).

    python -m claudon ~/.claude -o /tmp/r.html --redact
    python scripts/record_demo.py /tmp/r.html

Frames are lossless screenshots taken while the tour runs (Playwright's own video is low-bitrate).
"""
import subprocess, sys, tempfile, time
from pathlib import Path
from playwright.sync_api import sync_playwright

# Fade/slide new content in on every tab switch and modal open (recording only; the dashboard is untouched).
FX = """@keyframes in{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
#view>*{animation:in .45s ease-out}#modal>div{animation:in .35s ease-out}"""
report, out = Path(sys.argv[1]).resolve(), Path(__file__).parent.parent / "docs/assets"


def ff(*a):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *map(str, a)], check=True)


with sync_playwright() as p, tempfile.TemporaryDirectory() as tmp:
    b = p.chromium.launch()
    for scheme in ("light", "dark"):
        pg = b.new_context(viewport={"width": 1100, "height": 680}, color_scheme=scheme).new_page()
        d, shots = Path(tmp) / scheme, []
        d.mkdir()

        def hold(ms):  # keep screenshotting for ms so animations are captured
            end = time.time() + ms / 1000
            while time.time() < end:
                f = d / f"{len(shots):04d}.png"
                pg.screenshot(path=f)
                shots.append((f, time.time()))

        pg.goto(report.as_uri()); pg.add_style_tag(content=FX); hold(1500)
        pg.mouse.wheel(0, 500); hold(1200); pg.mouse.wheel(0, -500); hold(600)
        nav = pg.locator("#nav button")
        nav.nth(1).click(); hold(1200)  # Tasks
        pg.locator("tr[data-task]").first.click(); hold(2500)
        pg.keyboard.press("Escape"); hold(400)
        for i in range(2, nav.count()):
            nav.nth(i).click(); hold(1500)

        lst = d / "list.txt"  # concat demuxer with real per-frame durations
        lst.write_text("".join(f"file '{f}'\nduration {max(t2 - t1, .02):.3f}\n"
                               for (f, t1), (_, t2) in zip(shots, shots[1:])) + f"file '{shots[-1][0]}'\n")
        src = ["-f", "concat", "-safe", "0", "-i", lst]
        ff(*src, "-vf", "fps=15,scale=960:-1:flags=lanczos", "-loop", 0, "-quality", 90,
           "-compression_level", 6, out / f"demo-{scheme}.webp")
        if scheme == "dark":
            ff(*src, "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-crf", 18, "-preset", "slow",
               "-movflags", "+faststart", out / "demo-dark.mp4")
    b.close()
