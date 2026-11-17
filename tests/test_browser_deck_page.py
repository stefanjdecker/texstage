# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The presenter's deck page in a real browser (2026-11-15), as the browser smoke tests drive it
(test_browser_smoke.py: Playwright, the installed Chrome, a real server on a free port): a card says when
its deck was presented last and shows its first slide, the running lecture's card says Continue, the
order Recently presented, a phone-wide page that keeps a card's name on a line, and a deck taken off the
list coming back with Undo or Put back."""
from __future__ import annotations

from fake_bundle import make_bundle
from test_browser_smoke import WINDOW, browser, host, join, new_page, running, wait_until  # noqa: F401  (the fixtures)

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


def test_the_host_console_asks_before_a_build_ends_the_running_game(new_page, tmp_path):
    """The presenter window asked before a newer build of a deck ended its game with players (deck management, first
    package); the host console started the new build's game without a word - a new PIN, the phones dropped. It
    asks now, as the presenter window does: Keep the running build opens that game, Open this build ends it."""
    first = make_bundle(tmp_path / "bundles" / "first", deck="alpha", title="Alpha", stage="pdf")
    with running(tmp_path) as live:
        h, pin = host(live, first)                                  # the lecture: one phone in it
        phone = join(new_page, live, pin, "Ada")
        h.close()
        make_bundle(tmp_path / "bundles" / "second", deck="alpha", title="Alpha", time=30, stage="pdf")   # rebuilt
        page = new_page(**WINDOW)
        page.goto(f"{live.url}/host")
        page.locator(".deckcard button[data-i]").first.click()      # the deck's newest build: Start
        dialog = page.locator(".dialog")
        dialog.wait_for()
        assert f"PIN {pin}" in dialog.inner_text() and "1 player" in dialog.inner_text()
        page.get_by_role("button", name="Keep the running build").click()
        wait_until(page, f"(document.querySelector('#pin')?.textContent || '').replace(/\\D/g, '') === '{pin}'")
        page.locator("#decks").click()
        page.locator(".deckcard button[data-i]").first.click()
        page.get_by_role("button", name="Open this build").click()  # the new build: a new game
        wait_until(page, "(document.querySelector('#pin')?.textContent || '').replace(/\\D/g, '').length === 6 && "
                         f"(document.querySelector('#pin')?.textContent || '').replace(/\\D/g, '') !== '{pin}'")
        phone.close()


def test_select_moves_several_decks_into_a_new_folder_and_removes_them_with_undo(new_page, tmp_path):
    """Moving many decks went one at a time (the deck page's suggestion 6): Select ticks cards - Shift a range -,
    Move to … takes them all, into a folder made right there (New folder in the dialog), and Remove … takes them
    off the list at once, with Undo. A deck built meanwhile appears by itself (suggestion 5), and the menu of a
    card goes by the arrow keys (11)."""
    alpha, rdf, gamma = three_decks(tmp_path)
    with running(tmp_path) as live:
        page = deck_page(new_page, live)
        assert page.locator(".libhelp").get_attribute("open") is None          # the intro: folded
        card(page, "Alpha").locator("button.more").click()                     # the menu by the keys
        page.keyboard.press("ArrowDown")
        page.keyboard.press("ArrowDown")
        assert page.evaluate("document.activeElement.textContent") == "Rename …"
        page.keyboard.press("Escape")
        page.locator("#select").click()
        card(page, "02 RDF basics").click()
        card(page, "Gamma").click(modifiers=["Shift"])                         # the range: RDF to Gamma (by name)
        assert page.locator(".pickbar .count").inner_text() == "3 selected"   # (02 RDF basics, Alpha, Gamma)
        card(page, "Alpha").click()                                            # untick one
        assert page.locator(".pickbar .count").inner_text() == "2 selected"
        page.locator("[data-pickmove]").click()
        page.locator(".dialog [data-newfolder]").click()
        page.locator(".dialog .askfield").fill("Week 1")
        page.locator(".dialog [data-answer=yes]").last.click()
        card(page, "Week 1").wait_for()                                        # the folder, the two inside it
        page.locator(".hint.note", has_text="2 decks moved to Week 1").wait_for()   # (named: it was "undefined")
        assert page.locator(".deckcard[data-deck] .name").all_inner_texts() == ["Alpha"]
        card(page, "Week 1").click()
        wait_until(page, "document.querySelectorAll('.deckcard[data-deck]').length === 2")
        page.locator("#select").click()
        page.locator("[data-pickall]").click()
        page.locator("[data-pickremove]").click()
        assert "Take 2 decks off the list" in page.locator(".dialog .ask").inner_text()
        page.click(".dialog [data-answer=yes]")
        wait_until(page, "document.querySelectorAll('.deckcard[data-deck]').length === 0")
        page.locator(".hint.note button", has_text="Undo").click()
        wait_until(page, "document.querySelectorAll('.deckcard[data-deck]').length === 2")
        page.locator(".crumb[data-to='']").click()
        make_bundle(tmp_path / "bundles" / "delta", deck="delta", title="Delta", stage="pdf")   # built now
        card(page, "Delta").wait_for(timeout=20000)                          # ... and there, without a reload


def test_builds_say_what_changed_lectures_end_and_storage_counts(new_page, tmp_path):
    """Builds: what changed since the build before (suggestion 7). Lectures: End lecture … ends the open game at once
    (8). Storage: what the lecturer's decks hold on the server (10)."""
    alpha = make_bundle(tmp_path / "bundles" / "a1", deck="alpha", title="Alpha", stage="pdf")
    with running(tmp_path) as live:
        h, pin = host(live, alpha)
        phone = join(new_page, live, pin, "Ada")                               # (a lecture: it left a player)
        h.close()
        make_bundle(tmp_path / "bundles" / "a2", deck="alpha", title="Alpha", time=30, stage="pdf")   # quizzes' time
        page = deck_page(new_page, live)
        card(page, "Alpha").first.locator("button.more").click()
        page.get_by_role("menuitem", name="Builds …").click()
        changed = page.locator(".dialog .lecture").first.locator(".meta", has_text="Since the build before")
        changed.wait_for()
        assert changed.inner_text().startswith("Since the build before:") and "quizzes changed" in changed.inner_text()
        page.locator(".dialog [data-close]").click()
        card(page, "Alpha").first.locator("button.more").click()
        page.get_by_role("menuitem", name="Lectures …").click()
        page.locator(".dialog [data-act=end]").click()
        assert f"PIN {pin}" in page.locator(".dialog .ask").inner_text()
        page.locator(".dialog [data-answer=yes]").last.click()
        page.locator(".dialog .lecture .tag", has_text="ended").wait_for()
        page.locator(".dialog [data-close]").click()
        page.locator("#storage").click()
        rows = page.locator(".dialog .lecture")
        rows.first.wait_for()
        assert "1 lecture" in rows.first.inner_text() and "alpha" in rows.first.inner_text()
        page.locator(".dialog [data-close]").click()
        # a deck with two cards (its newest build, and the build its lecture played) is one deck to Select
        h2, pin2 = host(live, alpha)                                       # (a game on the older build again)
        page.reload()
        wait_until(page, "document.querySelectorAll('.deckcard[data-deck=alpha]').length === 2")
        page.locator("#select").click()
        card(page, "Alpha").first.click()
        assert page.locator(".pickbar .count").inner_text() == "1 selected"
        assert page.locator(".deckcard.picked").count() == 2                 # both its cards ticked
        page.locator("[data-pickremove]").click()
        question = page.locator(".dialog .ask").inner_text()
        assert "Take 1 deck off the list" in question and "1 of them is being presented now" in question
        page.locator(".dialog [data-answer=yes]").click()
        page.locator(".hint.note", has_text="1 deck removed").wait_for()
        assert page.locator(".dialog").count() == 0                          # (no error: removed once)
        h2.close()
        phone.close()
