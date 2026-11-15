# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The presenter window's Record in a real browser (2026-11-15), as the browser smoke tests drive it
(test_browser_smoke.py: Playwright, the installed Chrome, a real server on a free port). Once the screen is
chosen, the dialog closes and the recording waits in the top bar, not started and without a file - the screen
as a live miniature, Start, ✕ -, so that the lecturer puts right first what needs it. In a lecture, sharing an
entire screen took the full-screen presenter window out of full screen (Chromium on Windows: as the capture
starts, its "is sharing your screen" bar takes the focus), and a page may go back only in a click. A stand-in
for the browser's dialog and the capture's start does here what the browser did - it hands over a screen (a
canvas's stream) and leaves full screen -, and the window is full screen again: with Start, with ✕, or at once
while the click that opened the dialog still counts."""
from __future__ import annotations

from fake_bundle import make_bundle
from test_browser_smoke import DECK, browser, host, new_page, running  # noqa: F401  (the fixtures)

# a window smaller than its screen, so that its size alone is not full screen
LAPTOP = {"viewport": {"width": 1280, "height": 800}, "screen": {"width": 1920, "height": 1080}}

# the browser's dialog for the screen and the capture's start as Chromium behaved: the lecturer chooses
# (window.pickMs: how long), the capture starts and full screen ends (the sharing bar takes the focus), the
# screen is handed over (window.picked). A choice longer than the 5 s a click counts in Chromium: the click no
# longer counts - which the page reads in navigator.userActivation (here, under Playwright, a click counts
# longer: the stand-in says so as a lecture's browser would)
PICKER = """
navigator.mediaDevices.getDisplayMedia = async () => {
  await new Promise((done) => setTimeout(done, window.pickMs || 0));
  if (document.fullscreenElement) await document.exitFullscreen();
  if ((window.pickMs || 0) > 5000) {
    Object.defineProperty(navigator, "userActivation", { configurable: true,
      get: () => ({ isActive: false, hasBeenActive: true }) });
  }
  const canvas = document.createElement("canvas");
  canvas.width = 320; canvas.height = 180;
  const g = canvas.getContext("2d");
  g.fillStyle = "#335"; g.fillRect(0, 0, 320, 180);
  window.picked = canvas.captureStream(5);
  return window.picked;
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
    """Record, no microphone (none here), the screen chosen: the recording waits in the top bar."""
    page.evaluate(f"window.pickMs = {ms}")
    page.click("#recbtn")
    page.locator("#recpick:not([disabled])").wait_for()
    page.click("#recpick")
    page.locator("#rec.ready").wait_for(timeout=ms + 10000)


def takes(live) -> int:
    """Recordings the server has begun: a file for each."""
    return len(live.app.state.server.recordings.takes)


def test_the_chosen_screen_waits_until_start_which_records_it_full_screen_again(new_page, tmp_path):
    """The choice took longer than a click counts: the dialog closes, the recording waits - the chosen screen
    live as a miniature, nothing recorded, no file - and the window stays out of full screen until Start, a
    click, brings it back with the recording."""
    fb = make_bundle(tmp_path / "bundles", quizzes=DECK, stage="pdf")
    with running(tmp_path) as live:
        h, pin = host(live, fb)
        page = presenter(new_page, live, fb)
        full_screen(page)
        choose_screen(page, 6000)
        assert page.locator(".dialog").count() == 0                          # the presenter works meanwhile
        page.wait_for_function("() => document.querySelector('#recview').srcObject === window.picked")
        assert takes(live) == 0                                              # waiting: no file yet
        assert not page.evaluate("Boolean(document.fullscreenElement)")      # as the capture left it
        page.hover("#recview")                                               # the larger one, below the bar,
        page.locator("#recbig").wait_for()                                   # ... takes no click from Start
        page.click("#recgo")
        page.wait_for_function(FULL, timeout=5000)
        page.locator("#rec.recording").wait_for(timeout=10000)               # and it records
        assert takes(live) == 1
        h.close()


def test_a_quick_choice_is_full_screen_at_once_x_lets_it_go_and_a_window_not_full_screen_stays_so(new_page, tmp_path):
    """Chosen within the click's time, the window is full screen again at once; ✕ lets the waiting recording
    go - Record again, no file - and keeps full screen. A window that was not full screen before Record is not
    made so."""
    fb = make_bundle(tmp_path / "bundles", quizzes=DECK, stage="pdf")
    with running(tmp_path) as live:
        h, pin = host(live, fb)
        page = presenter(new_page, live, fb)
        full_screen(page)
        choose_screen(page, 0)
        page.wait_for_function(FULL, timeout=5000)                               # at once, before Start
        page.click("#recdrop")
        page.locator("#recbtn").wait_for()                                       # Record again
        assert page.evaluate("window.picked.getVideoTracks()[0].readyState") == "ended"   # the screen let go
        assert page.evaluate(FULL)
        assert takes(live) == 0
        page.evaluate("document.exitFullscreen()")
        page.wait_for_function("() => !document.fullscreenElement")
        choose_screen(page, 0)
        page.click("#recdrop")
        page.locator("#recbtn").wait_for()
        assert not page.evaluate("Boolean(document.fullscreenElement)")
        h.close()


def test_a_waiting_recording_whose_screen_goes_away_is_let_go(new_page, tmp_path):
    """Stop sharing in the browser's bar, the projector window closed, the display gone - before Start: nothing
    was recorded, the top bar offers Record again, and a notice says why."""
    fb = make_bundle(tmp_path / "bundles", quizzes=DECK, stage="pdf")
    with running(tmp_path) as live:
        h, pin = host(live, fb)
        page = presenter(new_page, live, fb)
        choose_screen(page, 0)
        page.evaluate("window.picked.getVideoTracks()[0].dispatchEvent(new Event('ended'))")
        page.locator("#recbtn").wait_for()
        page.get_by_text("went away before the recording started").wait_for()
        assert takes(live) == 0
        h.close()
