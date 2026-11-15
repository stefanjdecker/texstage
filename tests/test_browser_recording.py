# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The presenter window's Record in a real browser (2026-11-15), as the browser smoke tests drive it
(test_browser_smoke.py: Playwright, the installed Chrome, a real server on a free port). In a lecture the
browser's dialog for the screen took the full-screen presenter window out of full screen (Chromium on
Windows), and a page may go back to full screen only in a click. A stand-in for that dialog does here what
the browser did - it leaves full screen and hands over a screen (a canvas's stream) -, and the window is full
screen again: with Start, with Cancel, or at once while the click that opened the dialog still counts."""
from __future__ import annotations

from fake_bundle import make_bundle
from test_browser_smoke import DECK, browser, host, new_page, running  # noqa: F401  (the fixtures)

# a window smaller than its screen, so that its size alone is not full screen
LAPTOP = {"viewport": {"width": 1280, "height": 800}, "screen": {"width": 1920, "height": 1080}}

# the browser's dialog for the screen as Chromium behaved: it leaves full screen, the lecturer chooses
# (window.pickMs: how long), the screen is handed over. A choice longer than the 5 s a click counts in
# Chromium: the click no longer counts - which the page reads in navigator.userActivation (here, under
# Playwright, a click counts longer: the stand-in says so as a lecture's browser would)
PICKER = """
navigator.mediaDevices.getDisplayMedia = async () => {
  if (document.fullscreenElement) await document.exitFullscreen();
  await new Promise((done) => setTimeout(done, window.pickMs || 0));
  if ((window.pickMs || 0) > 5000) {
    Object.defineProperty(navigator, "userActivation", { configurable: true,
      get: () => ({ isActive: false, hasBeenActive: true }) });
  }
  const canvas = document.createElement("canvas");
  canvas.width = 320; canvas.height = 180;
  const g = canvas.getContext("2d");
  g.fillStyle = "#335"; g.fillRect(0, 0, 320, 180);
  return canvas.captureStream(5);
};
"""

FULL = "() => document.fullscreenElement === document.documentElement"


def presenter(new_page, live, fb):
    page = new_page(**LAPTOP)
    page.add_init_script(PICKER)
    page.goto(f"{live.url}/stage?bundle={fb.id}")
    page.wait_for_function("/PIN \\d/.test(document.querySelector('#pin')?.textContent || '')")
    page.locator("#recbtn").wait_for()
    return page


def full_screen(page):
    """The lecturer makes the window full screen - in a click, as the browser wants it."""
    page.evaluate("""() => { const b = document.createElement("button"); b.id = "fulltest"; b.textContent = "full";
        b.style = "position:fixed;left:0;top:0;z-index:99999";
        b.onclick = () => { b.remove(); document.documentElement.requestFullscreen(); };
        document.body.append(b); }""")
    page.click("#fulltest")
    page.wait_for_function(FULL)


def choose_screen(page, ms: int):
    page.evaluate(f"window.pickMs = {ms}")
    page.click("#recbtn")
    page.locator("#recpick:not([disabled])").wait_for()
    page.click("#recpick")
    page.locator("#recpreview:not([hidden])").wait_for(timeout=ms + 10000)


def test_the_presenter_window_is_full_screen_again_when_the_recording_starts(new_page, tmp_path):
    """The choice took longer than a click counts: the window stays out of full screen with the dialog and its
    miniature, and Start - a click - brings it back with the recording."""
    fb = make_bundle(tmp_path / "bundles", quizzes=DECK, stage="pdf")
    with running(tmp_path) as live:
        h, pin = host(live, fb)
        page = presenter(new_page, live, fb)
        full_screen(page)
        choose_screen(page, 6000)
        assert not page.evaluate("Boolean(document.fullscreenElement)")      # as the browser left it
        page.click("#recstart")
        page.wait_for_function(FULL, timeout=5000)
        page.locator("#rec.recording").wait_for(timeout=10000)                 # and it records
        h.close()


def test_a_quick_choice_and_cancel_keep_full_screen_and_a_window_not_full_screen_stays_so(new_page, tmp_path):
    """Chosen within the click's time, the window is full screen again at once; Cancel keeps it so. A window
    that was not full screen before Record is not made so."""
    fb = make_bundle(tmp_path / "bundles", quizzes=DECK, stage="pdf")
    with running(tmp_path) as live:
        h, pin = host(live, fb)
        page = presenter(new_page, live, fb)
        full_screen(page)
        choose_screen(page, 0)
        page.wait_for_function(FULL, timeout=5000)                               # at once, before Start
        page.click("#closedlg")
        page.wait_for_timeout(300)
        assert page.evaluate(FULL)
        page.evaluate("document.exitFullscreen()")
        page.wait_for_function("() => !document.fullscreenElement")
        choose_screen(page, 0)
        page.click("#closedlg")
        page.wait_for_timeout(500)
        assert not page.evaluate("Boolean(document.fullscreenElement)")
        h.close()
