# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The presenter's deck page in a real browser (2026-11-15), as the browser smoke tests drive it
(test_browser_smoke.py: Playwright, the installed Chrome, a real server on a free port): a card says when
its deck was presented last and shows its first slide, the running lecture's card says Continue, the
order Recently presented, a phone-wide page that keeps a card's name on a line, and a deck taken off the
list coming back with Undo or Put back."""
from __future__ import annotations

from fake_bundle import make_bundle
from test_browser_smoke import WINDOW, browser, host, new_page, running, wait_until  # noqa: F401  (the fixtures)

PHONE_WIDE = {"viewport": {"width": 390, "height": 844}, "is_mobile": True, "has_touch": True, "device_scale_factor": 2}


def three_decks(tmp_path):
    """Alpha, "02 RDF basics" and Gamma, each with its stage PDF (Present)."""
    return [make_bundle(tmp_path / "bundles" / deck, deck=deck, title=title, stage="pdf")
            for deck, title in (("alpha", "Alpha"), ("rdf", "02 RDF basics"), ("gamma", "Gamma"))]


def deck_page(new_page, live, **options):
    """The presenter window's deck page (this computer: its key without asking)."""
    page = new_page(**(options or WINDOW))
    page.goto(f"{live.url}/stage")
    page.locator(".deckcard").first.wait_for()
    return page


def card(page, name: str):
    return page.locator(".deckcard").filter(has=page.get_by_text(name, exact=True))


def test_the_running_lecture_continues_and_the_last_presented_comes_first(new_page, tmp_path):
    """Every card said Present, the running lecture's too, and when a deck was presented last no card said:
    finding today's deck meant reading build times. Now Continue (with its PIN) where the lecture runs,
    "presented today" on its card, the order Recently presented, and each card's first slide."""
    alpha, rdf, gamma = three_decks(tmp_path)
    with running(tmp_path) as live:
        h, pin = host(live, gamma)                                  # Gamma: its lecture runs
        page = deck_page(new_page, live)
        assert card(page, "Gamma").locator("[data-present]").inner_text() == "Continue"
        assert card(page, "Alpha").locator("[data-present]").inner_text() == "Present"
        assert f"game {pin}" in card(page, "Gamma").inner_text()
        assert "presented today" in card(page, "Gamma").locator(".meta").inner_text()
        assert "presented" not in card(page, "Alpha").locator(".meta").inner_text()
        wait_until(page, """() => { const imgs = [...document.querySelectorAll('.deckcard .thumb img')];
            return imgs.length === 3 && imgs.every((i) => i.complete && i.naturalWidth > 0); }""")
        assert page.locator(".deckcard .name").all_inner_texts() == ["02 RDF basics", "Alpha", "Gamma"]   # by name
        page.select_option(".libsort", "recent")
        assert page.locator(".deckcard .name").all_inner_texts() == ["Gamma", "02 RDF basics", "Alpha"]
        card(page, "Gamma").locator("[data-present]").click()       # back into it: the same game
        wait_until(page, f"(document.querySelector('#pin')?.textContent || '').replace(/\\D/g, '') === '{pin}'")
        h.close()


def test_a_card_on_a_phone_keeps_its_name_on_one_line(new_page, tmp_path):
    """On a phone (a paired device's deck page) a card with a tag squeezed its text to a word per line:
    "02 / RDF / basics", the details below it a word each. The tags and buttons now go below the text."""
    alpha, rdf, gamma = three_decks(tmp_path)
    with running(tmp_path) as live:
        h, pin = host(live, rdf)                                    # its card has the game's tag
        page = deck_page(new_page, live, **PHONE_WIDE)
        name = card(page, "02 RDF basics").locator(".name")
        line = card(page, "Alpha").locator(".name").bounding_box()["height"]
        assert name.bounding_box()["height"] < 1.5 * line            # one line, as Alpha's
        assert card(page, "02 RDF basics").locator(".info").bounding_box()["width"] > 150
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")   # nothing beside the page
        h.close()


def test_a_deck_removed_from_the_list_comes_back_with_undo_and_put_back(new_page, tmp_path):
    """Remove from the list took a deck off the page with no way back but its next build - its running
    lecture's card too, without a word. Now the question says the lecture runs (and goes on), the notice
    has Undo, and the decks taken off the list are below it, each with Put back."""
    alpha, rdf, gamma = three_decks(tmp_path)
    with running(tmp_path) as live:
        h, pin = host(live, alpha)                                   # Alpha: its lecture runs
        page = deck_page(new_page, live)

        def remove(name: str):
            card(page, name).locator("button.more").click()
            page.get_by_role("menuitem", name="Remove from the list …").click()
            return page.locator(".dialog .ask")

        question = remove("Alpha")
        assert f"A lecture of \"Alpha\" is running (PIN {pin}" in question.inner_text()
        page.click(".dialog [data-answer=yes]")
        card(page, "Alpha").wait_for(state="detached")
        undo = page.locator(".hint.note button", has_text="Undo")
        undo.click()
        card(page, "Alpha").wait_for()
        assert h.ask({"t": "slide", "slide": alpha.slides[1]["id"], "id": "s"})["t"] == "ok"   # it went on all along

        remove("Gamma")
        page.click(".dialog [data-answer=yes]")
        card(page, "Gamma").wait_for(state="detached")
        page.click(".removed summary")
        page.click("[data-put-back=gamma]")
        card(page, "Gamma").wait_for()
        assert page.locator(".removed").count() == 0                  # none left off the list
        h.close()
