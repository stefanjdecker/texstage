# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The game: sessions, players, rounds and answers as a synchronous state machine
(docs/design.md, section 6).

The engine never reads a clock: every call gets `now` (milliseconds since the epoch), so
tests drive it with a fake clock and the server (app.py) calls tick(now) when the next
deadline is due (next_deadline()). It never waits for anything either; persistence is a
write-through to a Store (store.py) - one transaction per call - or nothing (store=None).

The slides the lecturer shows drive the game (show_slide), every step idempotent:

    question slide        a round for the quiz unless it has one: get-ready (3 s), open (the
                          quiz's time), closed when the time is up, when every connected
                          player has answered, or when the lecturer skips
    reveal, answer and    close the round if still open, judge and score the answers,
    leaderboard slides    reveal
    podium slide          the game is finished: final standings
    join slide            nothing - after the podium: a new game (new PIN) for the next group
    other slides          nothing (the session itself is opened by the host's hello)

Going back never restarts a round; `again` asks a revealed question once more as a
practice round (no points) and rewinds the game there: the rounds of the later quizzes are
withdrawn, their points too, so those questions are asked anew. Answer keys and results leave the engine only in the views:
players get correctness and keys after the reveal, hosts the distribution once a round is
closed and the keys after the reveal.

A session also keeps what texstage's presenter window sets for the projector (screen:
live, black, white or the slide frozen; the presenter's timer) - in the host view as
`stage`, stored with the session. The timer goes on in the deck's next game (after the
podium, a restart, a rebuild), unless the session went stale (docs/texstage-design.md).

texstage M6 adds to a game: ad-hoc polls (polls.py) - quizzes of the game, asked when the
lecturer types them and revealed as soon as they close -, sketch questions (the phones
draw; the projector shows the sketches the lecturer picks), and questions from the audience
(qa.py). The projector shows a poll or picked sketches instead of the slide (`stage.poll`,
`stage.sketches`) until the lecturer goes on, and a question as a card over the slide
(`stage.question`).
"""
from __future__ import annotations

import hashlib
import secrets
import unicodedata
from collections import Counter
from dataclasses import dataclass, field, replace

from texstage.server import qa
from texstage.server import types as stage_types
from texstage.server.bundles import Bundle, QuizDef, SlideInfo
from texstage.server.ink import InkBook, Stroke, check_frame
from texstage.server.polls import POLLS_MAX, PollError, make_poll, poll_quiz
from texstage.server.qa import Asked
from texstage.server.scoring import InvalidAnswer, judge, normalize_text, speed_points, streak_bonus, validate

NICK_MAX = 20
CHOICE_TYPES = ("single", "truefalse", "multiple", "poll")
PLAYER_KEYS = ("correct", "order", "answer", "tolerance", "accept")
SCREENS = ("live", "black", "white", "freeze")      # what the projector shows (texstage)
TIMER_MAX_S = 24 * 3600
BOARDS = ("blank", "grid")                         # whiteboard pages
BOARDS_MAX = 200
SKETCHES_SHOWN = 12                                # on the projector at once
OVERLAYS = ("poll", "sketches")                    # shown instead of the slide, until the lecturer goes on


class GameError(Exception):
    """A command that cannot be carried out; `code` is for clients, the message for people."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class Settings:
    get_ready_ms: int = 3000
    grace_ms: int = 500                  # answers this late still count (network, clocks)
    stale_ms: int = 6 * 3600 * 1000      # a session idle this long is over (next lecture)
    streak_bonus: bool = True
    close_when_all_answered: bool = True
    max_players: int = 1000
    prepare_ms: int = 10 * 60 * 1000     # preparing the live slides ends by itself after this


@dataclass
class Player:
    id: str
    session: str
    nickname: str
    token_hash: str
    joined: int
    kicked: bool = False
    score: int = 0
    streak: int = 0
    total_ms: int = 0                    # answer time summed over scored rounds: breaks ties
    rank: int = 0                        # 0: no scored round revealed yet
    prev_rank: int = 0
    muted: bool = False                  # may not ask questions (qa.py)
    connections: int = 0                 # open connections (not stored)


@dataclass
class Answer:
    round: str
    player: str
    payload: dict
    received: int
    answer_ms: int
    correct: bool | None = None          # set at the reveal
    credit: float = 0.0
    points: int = 0
    bonus: int = 0
    sequence: int = 0                    # stable submission number within the round (sketch cursors)


@dataclass
class Round:
    id: str
    session: str
    quiz: str
    attempt: int
    practice: bool
    phase: str                           # get-ready open closed revealed
    started: int
    opens: int                           # moved on by pauses, so answer times exclude them
    deadline: int | None                 # None while paused
    limit_ms: int                        # the time limit (+ extensions)
    paused_left: int | None = None
    paused_at: int | None = None
    closed: int | None = None
    closed_by: str | None = None         # time skip all
    revealed: int | None = None
    answers: dict[str, Answer] = field(default_factory=dict)


@dataclass
class Session:
    id: str
    pin: str
    deck: str
    bundle: str
    created: int
    last_active: int
    owner: str = ""                      # the lecturer whose game it is (lecturers.py)
    ended: int | None = None
    finished: int | None = None          # podium shown
    slide: int | None = None             # the slide the lecturer shows
    current: str | None = None           # the round the phones show
    preparing_until: int | None = None   # the add-in prepares the live slides (not stored)
    idle_from: int | None = None         # the last activity before a window opened it again (not stored)
    stage: dict = field(default_factory=dict)   # texstage: screen, frozen slide, timer
    polls: dict = field(default_factory=dict)   # texstage M6: quiz id -> {public, keys} (polls.py)
    players: dict[str, Player] = field(default_factory=dict)
    rounds: dict[str, Round] = field(default_factory=dict)
    questions: dict[str, Asked] = field(default_factory=dict)  # from the audience (qa.py)
    quizdefs: dict[str, QuizDef] = field(default_factory=dict, repr=False)   # the polls' (not stored)

    def latest(self, quiz: str) -> Round | None:
        rounds = [r for r in self.rounds.values() if r.quiz == quiz]
        return max(rounds, key=lambda r: r.attempt) if rounds else None

    def active_players(self) -> list[Player]:
        return [p for p in self.players.values() if not p.kicked]


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def clean_nickname(nickname) -> str:
    if not isinstance(nickname, str):
        raise GameError("nickname", "a nickname is text")
    text = "".join(c for c in unicodedata.normalize("NFC", nickname) if not unicodedata.category(c).startswith("C"))
    text = " ".join(text.split())
    if not 1 <= len(text) <= NICK_MAX:
        raise GameError("nickname", f"a nickname has 1 to {NICK_MAX} characters")
    return text


class Engine:
    def __init__(self, bundles, store=None, settings: Settings | None = None):
        self.bundles = bundles               # .get(bundle id) -> Bundle | None
        self.store = store
        self.settings = settings or Settings()
        self.sessions: dict[str, Session] = {}
        self.players: dict[str, Player] = {}
        self.tokens: dict[str, str] = {}     # token hash -> player id
        self.ink = InkBook()                 # texstage: the strokes on the slides (ink.py)
        # the content types' larger data of all games (types.py: Book), and the games whose phones
        # get their state again after a type's change (all: True, or these player ids; take_due)
        self.books = {name: kind.Book() for name, kind in stage_types.TYPES.items() if hasattr(kind, "Book")}
        self.due: dict[str, set | bool] = {}
        if store is not None:
            for s in store.load():
                self._register(s)
            for stroke in store.load_strokes(list(self.sessions)):
                self.ink.add(stroke)
            for q in store.load_questions(list(self.sessions)):
                self.sessions[q.session].questions[q.id] = q
            for name, book in self.books.items():
                book.load([row for cls in getattr(stage_types.TYPES[name], "ROWS", {})
                           for row in store.load_rows(cls, list(self.sessions))])

    # ------------------------------------------------------------ bookkeeping
    def _register(self, s: Session):
        self.sessions[s.id] = s
        for p in s.players.values():
            self.players[p.id] = p
            self.tokens[p.token_hash] = p.id

    def _save(self, *items):
        if self.store is not None:
            for item in items:
                self.store.save(item)

    def _commit(self):
        if self.store is not None:
            self.store.commit()

    def session(self, sid: str) -> Session:
        s = self.sessions.get(sid)
        if s is None or s.ended is not None:
            raise GameError("no-session", "this game is over")
        return s

    def bundle(self, s: Session) -> Bundle:
        b = self.bundles.get(s.bundle)
        if b is None:
            raise GameError("unknown-bundle", f"bundle {s.bundle} is not on this server")
        return b

    def quiz(self, s: Session, quiz: str) -> QuizDef:
        """A quiz of the deck - or an ad-hoc poll of the game."""
        q = self.bundle(s).quizzes.get(quiz)
        if q is None and quiz in s.polls:
            q = s.quizdefs.get(quiz)
            if q is None:
                q = s.quizdefs[quiz] = poll_quiz(quiz, s.polls[quiz])
        if q is None:
            raise GameError("unknown-quiz", f"no quiz {quiz} in this deck")
        return q

    def quizzes(self, s: Session) -> list[str]:
        """The deck's quizzes, then the game's polls in the order they were asked."""
        return [*self.bundle(s).quizzes, *s.polls]

    def _new_pin(self) -> str:
        used = {s.pin for s in self.sessions.values() if s.ended is None}
        while True:
            pin = f"{secrets.randbelow(900000) + 100000}"
            if pin not in used:
                return pin

    # ------------------------------------------------------------ sessions (host)
    def open_session(self, deck: str, bundle_id: str, now: int, owner: str = "") -> Session:
        """The lecturer's active session of a deck - a new one if there is none, if it is
        stale (idle for hours: the next lecture) or if it plays an older build of the deck.
        Lecturers never share a game, even of decks with the same name."""
        b = self.bundles.get(bundle_id)
        if b is None or b.deck != deck:
            raise GameError("unknown-bundle", f"deck {deck}, bundle {bundle_id} is not on this server")
        last = None
        for s in list(self.sessions.values()):
            if s.deck == deck and s.owner == owner and s.ended is None:
                fresh = now - s.last_active < self.settings.stale_ms
                if s.bundle == bundle_id and fresh:
                    s.idle_from, s.last_active = s.last_active, now
                    self._save(s)
                    self._commit()
                    return s
                if fresh:
                    last = s                         # a rebuild in the lecture: the timer goes on
                self._end(s, now)
        s = self._create(b, now, owner, last)
        self._commit()
        return s

    def _create(self, b: Bundle, now: int, owner: str, last: Session | None = None) -> Session:
        """A new game. From the deck's last one (`last`, not ended yet) it takes over the
        presenter's timer and - the same build - the whiteboard pages and the ink."""
        stage: dict = {}
        same = last is not None and last.bundle == b.id
        if last is not None and last.stage.get("timer"):
            stage["timer"] = dict(last.stage["timer"])
        if last is not None and last.stage.get("qa"):
            stage["qa"] = True                           # questions stay open (not the old game's questions)
        if same and last.stage.get("boards"):
            stage["boards"] = [dict(x) for x in last.stage["boards"]]
        s = Session(secrets.token_hex(8), self._new_pin(), b.deck, b.id, now, now, owner, stage=stage)
        self._register(s)
        self._save(s)
        if same:
            self._save(*self.ink.move(last.id, s.id))
        return s

    def _end(self, s: Session, now: int):
        s.ended = now
        self._save(s)
        del self.sessions[s.id]
        for p in s.players.values():
            self.players.pop(p.id, None)
            self.tokens.pop(p.token_hash, None)
        self.ink.forget(s.id)
        for book in self.books.values():
            book.forget(s.id)
        self.due.pop(s.id, None)

    def end(self, sid: str, now: int):
        """Ends a game (its deck is deleted): what a new game of the deck would do with it - its
        results, ink and pages stay in the archive."""
        self._end(self.session(sid), now)
        self._commit()

    def restart(self, sid: str, now: int) -> Session:
        """A new game for the same deck (new PIN; the players join again)."""
        s = self.session(sid)
        b = self.bundle(s)
        new = self._create(b, now, s.owner, s)
        self._end(s, now)
        self._commit()
        return new

    # ------------------------------------------------------------ a new presentation, or the lecture continued (texstage)
    def marks(self, s: Session) -> tuple[int, int]:
        """The frames with ink and the whiteboard pages of an open game."""
        frames = {st.frame for st in self.ink.strokes.get(s.id, {}).values() if st.erased is None}
        return len(frames), len(s.stage.get("boards") or [])

    def earlier(self, sid: str) -> dict | None:
        """What a presenter window that opens the deck asks about: the ink and the whiteboard
        pages of this game - or, while it has none, those of the deck's last ended game of the
        same build (the lecture before) -, and when that lecture was active last."""
        s = self.session(sid)
        frames, boards = self.marks(s)
        if frames or boards:
            return {"game": s.id, "open": True, "at": s.idle_from or s.last_active, "frames": frames, "boards": boards}
        before = self.store.last_marked(s.deck, s.bundle, s.owner) if self.store is not None else None
        if before is None:
            return None
        return {"game": before["id"], "open": False, "at": before["last_active"], "frames": before["frames"],
                "boards": before["boards"]}

    def fresh(self, sid: str, now: int) -> Session:
        """A new presentation of the deck: a new game without the ink, the whiteboard pages and
        the timer of this one, which ends - its ink and pages stay with it in the archive."""
        s = self.session(sid)
        new = self._create(self.bundle(s), now, s.owner)
        self._end(s, now)
        self._commit()
        return new

    def take_over(self, sid: str, game, now: int) -> dict:
        """The continuation of an earlier lecture: this game, still without ink and whiteboard
        pages of its own, gets those of `game` - an ended game of the same deck, build and
        lecturer - as copies, so that lecture keeps its own in the archive."""
        s = self.session(sid)
        if any(self.marks(s)):
            raise GameError("invalid", "this game has ink or whiteboard pages of its own")
        old = self.store.ended_session(game) if self.store is not None and isinstance(game, str) else None
        if old is None or (old.deck, old.bundle, old.owner) != (s.deck, s.bundle, s.owner):
            raise GameError("invalid", "no earlier lecture of this build of the deck")
        copies = [replace(st, id=f"{st.id[:28]}-{secrets.token_hex(5)}", session=s.id)
                  for st in self.store.load_strokes([old.id])]
        for st in copies:
            self.ink.add(st)
        if old.stage.get("boards"):
            s.stage["boards"] = [dict(x) for x in old.stage["boards"]]
        s.last_active = now
        self._save(s, *copies)
        self._commit()
        frames, boards = self.marks(s)
        return {"frames": frames, "boards": boards}

    def show_slide(self, sid: str, slide: int, now: int) -> Session:
        """The session that is active afterwards: a new one when the join slide is shown
        after the podium (the deck presented to the next group)."""
        s = self.session(sid)
        b = self.bundle(s)
        info = b.slides.get(slide)
        before = self._shows(s, b)
        for key in ("board", *OVERLAYS):                 # a slide of the deck again: no whiteboard page,
            s.stage.pop(key, None)                       # no poll or sketches instead of it
        if slide != s.slide:
            s.stage.pop("zoom", None)                    # (texstage) the zoom ends with the slide
        self._types_shown(s, b, before, info, now)      # ... and a video it does not show stops
        if self._preparing(s, now):
            s.slide = slide                      # the add-in prepares the slides: nothing starts
            s.last_active = now
            self._save(s)
            self._commit()
            return s
        if info is not None and info.phase == "join" and s.finished is not None:
            new = self._create(b, now, s.owner, s)
            self._end(s, now)
            new.slide = slide
            self._save(new)
            self._commit()
            return new
        self._advance(s, now)
        s.slide = slide
        s.last_active = now
        if info is not None and info.phase == "read":
            # the question alone: the class reads it, the phones show it; the lecturer's
            # click to the question slide starts the round. A round already there (the
            # lecturer stepped back) stays the current one.
            r = s.latest(info.quiz)
            s.current = r.id if r is not None else None
        elif info is not None and info.phase == "question":
            r = s.latest(info.quiz) or self._start_round(s, info.quiz, False, now)
            s.current = r.id
            s.finished = None
        elif info is not None and info.phase in ("reveal", "answer", "leaderboard"):
            r = s.latest(info.quiz)
            if r is not None:
                self._reveal(s, r, now)
                s.current = r.id
        elif info is not None and info.phase == "podium":
            s.finished = s.finished or now
        self._save(s)
        self._commit()
        return s

    # ------------------------------------------------------------ preparing (host)
    def prepare(self, sid: str, on: bool, now: int) -> None:
        """The add-in shows every live slide once before the lecture, so that PowerPoint has
        started their add-ins - a first start shows seconds of white and black. Meanwhile the
        slides it shows start, reveal and finish nothing, and the phones stay where they are.
        Off again by the add-in, or by itself after Settings.prepare_ms."""
        s = self.session(sid)
        s.preparing_until = now + self.settings.prepare_ms if on else None

    @staticmethod
    def _preparing(s: Session, now: int) -> bool:
        return s.preparing_until is not None and now < s.preparing_until

    # ------------------------------------------------------------ rounds (host)
    def _start_round(self, s: Session, quiz: str, practice: bool, now: int) -> Round:
        q = self.quiz(s, quiz)
        attempt = 1 + sum(1 for r in s.rounds.values() if r.quiz == quiz)
        opens = now + self.settings.get_ready_ms
        r = Round(secrets.token_hex(8), s.id, quiz, attempt, practice, "get-ready", now, opens,
                  opens + q.time * 1000, q.time * 1000)
        s.rounds[r.id] = r
        self._advance(s, now)
        self._save(r)
        return r

    def _round(self, s: Session, quiz: str | None) -> Round:
        r = s.latest(quiz) if quiz else s.rounds.get(s.current or "")
        if r is None:
            raise GameError("no-round", "no question has been asked yet")
        return r

    def _close(self, r: Round, at: int, by: str):
        r.phase = "closed"
        r.closed = at
        r.closed_by = by
        r.deadline = r.deadline if r.deadline is not None else at
        r.paused_left = r.paused_at = None
        self._save(r)

    def _advance(self, s: Session, now: int) -> bool:
        """Due phase changes: get-ready -> open -> closed (-> revealed, for a poll of the game,
        once answers that are late by the grace period cannot come any more)."""
        changed = False
        for r in s.rounds.values():
            if r.phase == "get-ready" and now >= r.opens:
                r.phase = "open"
                changed = True
                self._save(r)
            if r.phase == "open" and r.deadline is not None and now >= r.deadline:
                self._close(r, r.deadline, "time")
                changed = True
            if r.phase == "closed" and self._auto(s, r) and now >= r.closed + self.settings.grace_ms:
                self._reveal(s, r, now)
                changed = True
        return changed

    def _auto(self, s: Session, r: Round) -> bool:
        """Whether the round's quiz shows its results as soon as it closes (ad-hoc polls)."""
        return self.quiz(s, r.quiz).reveal == "auto"

    def _close_now(self, s: Session, r: Round, now: int, by: str):
        """The lecturer stopped the round, or every player answered."""
        self._close(r, now, by)
        if self._auto(s, r):
            self._reveal(s, r, now)

    def skip(self, sid: str, quiz: str | None, now: int):
        s = self.session(sid)
        self._advance(s, now)
        r = self._round(s, quiz)
        if r.phase in ("get-ready", "open"):
            self._close_now(s, r, now, "skip")
        self._commit()

    def extend(self, sid: str, quiz: str | None, seconds: int, now: int):
        if not isinstance(seconds, int) or not 1 <= seconds <= 300:
            raise GameError("invalid", "extend by 1 to 300 seconds")
        s = self.session(sid)
        self._advance(s, now)
        r = self._round(s, quiz)
        if r.phase not in ("get-ready", "open"):
            raise GameError("closed", "the question is closed")
        r.limit_ms += seconds * 1000
        if r.paused_left is not None:
            r.paused_left += seconds * 1000
        else:
            r.deadline += seconds * 1000
        self._save(r)
        self._commit()

    def pause(self, sid: str, quiz: str | None, now: int):
        s = self.session(sid)
        self._advance(s, now)
        r = self._round(s, quiz)
        if r.phase != "open" or r.paused_left is not None:
            raise GameError("not-open", "only an open question can be paused")
        r.paused_left, r.paused_at, r.deadline = r.deadline - now, now, None
        self._save(r)
        self._commit()

    def resume(self, sid: str, quiz: str | None, now: int):
        s = self.session(sid)
        r = self._round(s, quiz)
        if r.paused_left is None:
            raise GameError("not-paused", "the question is not paused")
        r.opens += now - r.paused_at            # answer times leave the pause out
        r.deadline = now + r.paused_left
        r.paused_left = r.paused_at = None
        self._save(r)
        self._commit()

    def reveal(self, sid: str, quiz: str | None, now: int):
        """Close (if needed), score and reveal - what a reveal slide does, as a command: for
        a practice round, or a quiz whose answer comes without an answer frame."""
        s = self.session(sid)
        self._advance(s, now)
        r = self._round(s, quiz)
        self._reveal(s, r, now)
        s.current = r.id
        self._save(s)
        self._commit()

    def again(self, sid: str, quiz: str | None, now: int) -> Round:
        """Ask a revealed question once more, as practice (no points) - and rewind the game
        there: the rounds of the quizzes after it in the deck are withdrawn, points and all, so
        those questions are asked anew when their slides come. Going back never restarts a
        round, so without this a game played through once (a test run, or a lecture restarted
        after an interruption) would show only old results from here on."""
        s = self.session(sid)
        last = self._round(s, quiz)
        if last.phase != "revealed":
            raise GameError("busy", "the question has not been revealed yet")
        self._withdraw_after(s, last.quiz)
        r = self._start_round(s, last.quiz, True, now)
        s.current = r.id
        s.finished = None
        self._save(s)
        self._commit()
        return r

    def _quiz_order(self, s: Session) -> list[str]:
        """The deck's quizzes in the order of their first slide."""
        order = []
        for info in sorted(self.bundle(s).slides.values(), key=lambda i: i.index):
            if info.quiz and info.quiz not in order:
                order.append(info.quiz)
        return order

    def _withdraw_after(self, s: Session, quiz: str):
        """Every round of the quizzes after `quiz` in the deck goes, with its answers; the
        scores are counted again without them."""
        order = self._quiz_order(s)
        later = set(order[order.index(quiz) + 1:]) if quiz in order else set()
        gone = [r for r in s.rounds.values() if r.quiz in later]
        for r in gone:
            del s.rounds[r.id]
            if self.store is not None:
                self.store.delete_round(r.id)
        if s.current in {r.id for r in gone}:
            s.current = None
        if any(r.phase == "revealed" and not r.practice and self.quiz(s, r.quiz).scored for r in gone):
            self._rescore(s)

    def _rescore(self, s: Session):
        """Scores, streaks, streak bonuses and ranks from the rounds the game still has,
        replayed in the order they were revealed - as if the withdrawn ones had never run."""
        players = s.active_players()
        for p in players:
            p.score = p.streak = p.total_ms = p.rank = p.prev_rank = 0
        for r in sorted(s.rounds.values(), key=lambda r: (r.revealed or 0, r.started)):
            if r.phase != "revealed" or r.practice or not self.quiz(s, r.quiz).scored:
                continue
            for p in players:
                a = r.answers.get(p.id)
                if a is not None and a.correct:
                    p.streak += 1
                    a.bonus = streak_bonus(p.streak) if self.settings.streak_bonus else 0
                else:
                    p.streak = 0
                if a is not None:
                    p.score += a.points + a.bonus
                    p.total_ms += a.answer_ms
                    self._save(a)
            self._rank(s)
        for p in players:
            self._save(p)

    def finish(self, sid: str, now: int):
        s = self.session(sid)
        s.finished = s.finished or now
        self._save(s)
        self._commit()

    def _reveal(self, s: Session, r: Round, now: int):
        if r.phase in ("get-ready", "open"):
            self._close(r, now, "skip")
        if r.phase != "closed":
            return
        q = self.quiz(s, r.quiz)
        scored = q.scored and not r.practice
        for p in s.active_players():
            a = r.answers.get(p.id)
            if a is not None:
                verdict = judge(q, a.payload)
                a.correct, a.credit = verdict.correct, verdict.credit
                if scored:
                    a.points = int(speed_points(q.base, a.answer_ms, r.limit_ms) * verdict.credit + 0.5)
            if scored:
                if a is not None and a.correct:
                    p.streak += 1
                    a.bonus = streak_bonus(p.streak) if self.settings.streak_bonus else 0
                else:
                    p.streak = 0
                if a is not None:
                    p.score += a.points + a.bonus
                    p.total_ms += a.answer_ms
                self._save(p)
            if a is not None:
                self._save(a)
        r.phase = "revealed"
        r.revealed = now
        self._save(r)
        if scored:
            self._rank(s)

    def _rank(self, s: Session):
        ranked = sorted(s.active_players(), key=lambda p: (-p.score, p.total_ms, p.joined))
        for i, p in enumerate(ranked, 1):
            p.prev_rank, p.rank = p.rank, i
            self._save(p)

    # ------------------------------------------------------------ players
    def join(self, pin, nickname, now: int) -> tuple[Player, str]:
        s = next((s for s in self.sessions.values() if s.pin == pin and s.ended is None), None)
        if s is None:
            raise GameError("unknown-pin", "no game with this PIN")
        nick = clean_nickname(nickname)
        active = s.active_players()
        if any(p.nickname.casefold() == nick.casefold() for p in active):
            raise GameError("nickname-taken", "this nickname is taken")
        if len(active) >= self.settings.max_players:
            raise GameError("full", "the game is full")
        token = secrets.token_urlsafe(24)
        p = Player(secrets.token_hex(8), s.id, nick, token_hash(token), now)
        s.players[p.id] = p
        self.players[p.id] = p
        self.tokens[p.token_hash] = p.id
        self._save(p)
        self._commit()
        return p, token

    def player_by_token(self, token) -> Player:
        pid = self.tokens.get(token_hash(token)) if isinstance(token, str) else None
        if pid is None:
            raise GameError("unknown-player", "please join the game again")
        p = self.players[pid]
        if p.kicked:
            raise GameError("kicked", "you have been removed from the game")
        return p

    def kick(self, sid: str, pid: str, now: int):
        s = self.session(sid)
        p = s.players.get(pid)
        if p is None:
            raise GameError("unknown-player", "no such player")
        p.kicked = True
        self._save(p)
        shown = s.stage.get("sketches")
        if shown and pid in shown["players"]:
            shown["players"] = [other for other in shown["players"] if other != pid]
            if not shown["players"]:
                s.stage.pop("sketches")
            self._save(s)
        if p.rank:                               # close the gap in the standings
            self._rank(s)
        self._commit()

    def rename(self, sid: str, pid: str, nickname, now: int):
        s = self.session(sid)
        p = s.players.get(pid)
        if p is None:
            raise GameError("unknown-player", "no such player")
        nick = clean_nickname(nickname)
        if any(o.nickname.casefold() == nick.casefold() for o in s.active_players() if o is not p):
            raise GameError("nickname-taken", "this nickname is taken")
        p.nickname = nick
        self._save(p)
        self._commit()

    def answer(self, pid: str, rid: str, payload, now: int) -> Answer:
        p = self.players.get(pid)
        if p is None or p.kicked:
            raise GameError("unknown-player", "please join the game again")
        s = self.session(p.session)
        self._advance(s, now)
        r = s.rounds.get(rid)
        if r is None:
            raise GameError("unknown-round", "no such question")
        if r.phase == "get-ready":
            raise GameError("not-open", "the question is not open yet")
        late = r.phase == "closed" and r.closed_by == "time" and now <= r.closed + self.settings.grace_ms
        if r.phase != "open" and not late:
            raise GameError("closed", "time is up")
        if r.paused_left is not None:
            raise GameError("paused", "the question is paused")
        if pid in r.answers:
            raise GameError("already-answered", "you have answered already")
        try:
            canonical = validate(self.quiz(s, r.quiz), payload)
        except InvalidAnswer as err:
            raise GameError("invalid", str(err)) from None
        a = Answer(r.id, pid, canonical, now, min(max(now - r.opens, 0), r.limit_ms),
                   sequence=max((a.sequence for a in r.answers.values()), default=0) + 1)
        if self.store is not None:
            self.store.insert_answer(a)          # unique per round and player
        r.answers[pid] = a
        s.last_active = now
        self._save(s)
        if r.phase == "open" and self.settings.close_when_all_answered:
            connected = [o for o in s.active_players() if o.connections > 0]
            if connected and all(o.id in r.answers for o in connected):
                self._close_now(s, r, now, "all")
        self._commit()
        return a

    def connect(self, pid: str, delta: int):
        p = self.players.get(pid)
        if p is not None:
            p.connections = max(0, p.connections + delta)

    # ------------------------------------------------------------ the stage (texstage)
    def screen(self, sid: str, mode, now: int):
        """What the projector shows: the slide (live), black, white, or the slide shown now,
        frozen while the lecturer goes on (the game follows the lecturer all the same)."""
        s = self.session(sid)
        if mode not in SCREENS:
            raise GameError("invalid", f"the screen is {', '.join(SCREENS)}")
        stage = {k: v for k, v in s.stage.items() if k not in ("screen", "frozen", "frozen_board")}
        if mode != "live":
            stage["screen"] = mode
        if mode == "freeze":
            stage["frozen"] = s.slide
            if s.stage.get("board"):
                stage["frozen_board"] = s.stage["board"]          # a whiteboard page, not the slide
        s.stage = stage
        s.last_active = now
        self._save(s)
        self._commit()

    def timer(self, sid: str, action, seconds: int | None, now: int):
        """The presenter's timer: start, pause, reset, or a target (seconds; none: no target).
        It has run elapsed + (now - since) ms, since being None while it stands."""
        s = self.session(sid)
        t = {"since": None, "elapsed": 0, "target": None, **s.stage.get("timer", {})}
        if action == "start":
            if t["since"] is None:
                t["since"] = now
        elif action == "pause":
            if t["since"] is not None:
                t["elapsed"] += now - t["since"]
                t["since"] = None
        elif action == "reset":
            t["since"], t["elapsed"] = None, 0
        elif action == "target":
            if seconds is not None and not 0 <= seconds <= TIMER_MAX_S:
                raise GameError("invalid", f"a target has 0 to {TIMER_MAX_S} seconds")
            t["target"] = seconds * 1000 if seconds else None
        else:
            raise GameError("invalid", "the timer can start, pause, reset or take a target")
        s.stage = {**s.stage, "timer": t}
        s.last_active = now
        self._save(s)
        self._commit()

    def zoom(self, sid: str, rect, now: int):
        """The part of the slide the projector shows magnified ({x, y, w, h}, fractions of the
        slide; None: the whole slide). It ends with the slide (show_slide)."""
        s = self.session(sid)
        if rect is None:
            s.stage.pop("zoom", None)
        else:
            numbers = isinstance(rect, dict) and all(
                isinstance(rect.get(k), (int, float)) and not isinstance(rect.get(k), bool) for k in "xywh")
            if not numbers:
                raise GameError("invalid", "zoom: {x, y, w, h}, fractions of the slide")
            w, h = (min(1.0, max(0.02, float(rect[k]))) for k in "wh")
            x, y = min(1 - w, max(0.0, float(rect["x"]))), min(1 - h, max(0.0, float(rect["y"])))
            s.stage["zoom"] = {"x": round(x, 4), "y": round(y, 4), "w": round(w, 4), "h": round(h, 4)}
        s.last_active = now
        self._save(s)
        self._commit()

    def board_add(self, sid: str, after, kind, now: int) -> str:
        """A whiteboard page (blank or grid) after frame `after`; its id."""
        s = self.session(sid)
        if kind not in BOARDS:
            raise GameError("invalid", f"a whiteboard page is {' or '.join(BOARDS)}")
        if isinstance(after, bool) or not isinstance(after, int) or not 0 <= after <= 99999:
            raise GameError("invalid", "after: the number of the frame the page follows")
        boards = s.stage.setdefault("boards", [])
        if len(boards) >= BOARDS_MAX:
            raise GameError("too-many-boards", f"at most {BOARDS_MAX} whiteboard pages")
        board = secrets.token_hex(4)
        boards.append({"id": board, "after": after, "kind": kind})
        s.last_active = now
        self._save(s)
        self._commit()
        return board

    def go_board(self, sid: str, board, now: int):
        """The projector shows a whiteboard page; the game stays at its slide."""
        s = self.session(sid)
        if not any(x["id"] == board for x in s.stage.get("boards", [])):
            raise GameError("invalid", f"no whiteboard page {board!r}")
        before = self._shows(s, self.bundle(s))
        s.stage["board"] = board
        for key in ("zoom", *OVERLAYS):
            s.stage.pop(key, None)
        self._types_shown(s, self.bundle(s), before, None, now)
        s.last_active = now
        self._save(s)
        self._commit()

    def _shows(self, s: Session, b: Bundle) -> SlideInfo | None:
        """The slide the projector shows; None: a whiteboard page, a poll or sketches instead."""
        return None if any(s.stage.get(k) for k in ("board", *OVERLAYS)) else b.slides.get(s.slide)

    def _types_shown(self, s: Session, b: Bundle, before: SlideInfo | None, after: SlideInfo | None, now: int):
        """The content types' part when the projector shows something else (types.py): a video
        the new slide does not show stops where it is, one it brings that plays by itself starts;
        a type whose phones show its state has them get it again."""
        for name, kind in stage_types.TYPES.items():
            old = s.stage
            s.stage = kind.slide(s.stage, b.items.get(name, {}), before.shows.get(name, ()) if before else (),
                                 after.shows.get(name, ()) if after else (), now)
            if s.stage is not old and hasattr(kind, "player_view"):
                self._due(s.id, True)

    def _call(self, s: Session, kind, now: int, **who) -> stage_types.Call:
        b = self.bundle(s)
        return stage_types.Call(s, b.items.get(kind.NAME, {}), (b.keys.get("items") or {}).get(kind.NAME, {}), now,
                                self.books.get(kind.NAME), save=self._save, **who)

    def _due(self, sid: str, phones):
        """These phones of the game (True: all) get their state again (app.py, after the message)."""
        if phones is True or self.due.get(sid) is True:
            self.due[sid] = True
        elif phones:
            self.due.setdefault(sid, set()).update(phones)

    def take_due(self) -> dict[str, set | bool]:
        due, self.due = self.due, {}
        return due

    def type_message(self, sid: str, t: str, msg: dict, now: int, role: str | None = None,
                     conn: str | None = None) -> dict | None:
        """A message of a content type from a texstage window (a video's play, pause, seek;
        types.py) - one that changes the stage or only reads; the reply's fields."""
        s = self.session(sid)
        kind = stage_types.MESSAGES[t]
        call = self._call(s, kind, now, role=role, conn=conn)
        try:
            reply = kind.handle(call, t, msg)
        except stage_types.Refused as err:
            raise GameError(err.code, str(err)) from None
        except ValueError as err:
            raise GameError("invalid", f"{t}: {err}") from None
        if t not in stage_types.READS and call.changed:
            s.last_active = now
            self._save(s)
        self._commit()
        self._due(s.id, call.phones)
        return reply

    def type_player_message(self, pid: str, t: str, msg: dict, now: int) -> dict | None:
        """A phone's message to a content type (types.py: PLAYER_MESSAGES); the reply's fields."""
        p = self.players.get(pid)
        if p is None or p.kicked:
            raise GameError("unknown-player", "please join the game again")
        s = self.session(p.session)
        kind = stage_types.PLAYER_MESSAGES[t]
        call = self._call(s, kind, now, role="player", player=p)
        try:
            reply = kind.player(call, t, msg)
        except stage_types.Refused as err:
            raise GameError(err.code, str(err)) from None
        except ValueError as err:
            raise GameError("invalid", str(err)) from None
        s.last_active = now
        self._save(s)
        self._commit()
        self._due(s.id, call.phones)
        return reply

    def activity_checked(self, sid: str, aid: str, msg: dict, now: int) -> None:
        """F0's spike (server/spike_checks.py): a check from the server's pool, applied as the
        presenter window's result would be; the phones it concerns are due."""
        s = self.sessions.get(sid)
        if s is None:
            return
        kind = stage_types.TYPES["activity"]
        call = self._call(s, kind, now, role="pool")
        try:
            kind.checked(call, aid, msg)
        except stage_types.Refused as err:
            import logging
            logging.getLogger("texstage.spike").warning("a check not applied: %s", err)
            return
        self._save(s)
        self._commit()
        self._due(s.id, call.phones)

    def type_archive(self, sid: str, now: int) -> dict[str, str]:
        """The content types' files for the game's folder in the lecture archive: {name: text}."""
        s = self.session(sid)
        files: dict[str, str] = {}
        for kind in stage_types.TYPES.values():
            if hasattr(kind, "archive"):
                files.update(kind.archive(self._call(s, kind, now)))
        return files

    def left(self, conn: str):
        """A texstage window has gone: what it held (a type's lease, types.py: Book) is free."""
        for book in self.books.values():
            if hasattr(book, "left"):
                book.left(conn)

    @staticmethod
    def _stage_view(s: Session) -> dict:
        shown = s.questions.get(s.stage.get("question") or "")
        return {**{name: kind.view(s.stage) for name, kind in stage_types.TYPES.items()},
                "screen": s.stage.get("screen", "live"), "frozen": s.stage.get("frozen"),
                "frozen_board": s.stage.get("frozen_board"),
                "timer": {"since": None, "elapsed": 0, "target": None, **s.stage.get("timer", {})},
                "zoom": s.stage.get("zoom"), "board": s.stage.get("board"), "boards": s.stage.get("boards", []),
                "poll": s.stage.get("poll"), "sketches": s.stage.get("sketches"),
                "question": {"id": shown.id, "text": shown.text, "votes": len(shown.votes)} if shown else None}

    # ------------------------------------------------------------ ad-hoc polls (texstage M6, polls.py)
    def poll_create(self, sid: str, spec, now: int) -> str:
        """A poll the lecturer types during the lecture: a quiz of the game, asked at once - its
        round starts, the phones show it, the projector shows its poll slide. Its id."""
        s = self.session(sid)
        if len(s.polls) >= POLLS_MAX:
            raise GameError("too-many-polls", f"at most {POLLS_MAX} polls in a game")
        try:
            public, keys = make_poll(spec, self.bundle(s).language)
        except PollError as err:
            raise GameError(err.code, str(err)) from None
        taken = set(self.quizzes(s))
        n = len(s.polls) + 1
        while f"poll-{n}" in taken:
            n += 1
        quiz = f"poll-{n}"
        s.polls[quiz] = {"public": public, "keys": keys}
        r = self._start_round(s, quiz, False, now)
        s.current = r.id
        s.finished = None
        before = self._shows(s, self.bundle(s))
        s.stage["poll"] = quiz
        s.stage.pop("sketches", None)
        self._types_shown(s, self.bundle(s), before, None, now)
        s.last_active = now
        self._save(s)
        self._commit()
        return quiz

    def poll_show(self, sid: str, quiz, now: int):
        """The projector shows a poll of the game - its question, then its results - instead of
        the slide; None: the slide again."""
        s = self.session(sid)
        before = self._shows(s, self.bundle(s))
        if quiz is None:
            s.stage.pop("poll", None)
        elif isinstance(quiz, str) and quiz in s.polls:
            s.stage["poll"] = quiz
            s.stage.pop("sketches", None)
        else:
            raise GameError("invalid", f"no poll {quiz!r} in this game")
        self._types_shown(s, self.bundle(s), before, self._shows(s, self.bundle(s)), now)
        s.last_active = now
        self._save(s)
        self._commit()

    # ------------------------------------------------------------ sketches (texstage M6)
    def _sketch_round(self, s: Session, quiz) -> Round | None:
        if not isinstance(quiz, str) or self.quiz(s, quiz).type != "sketch":
            raise GameError("invalid", f"{quiz!r} is not a sketch question")
        return s.latest(quiz)

    @staticmethod
    def _sketches(s: Session, r: Round | None) -> list[Answer]:
        """A round's sketches in the order they came (their numbers in the gallery)."""
        if r is None:
            return []
        return sorted((a for pid, a in r.answers.items() if not s.players[pid].kicked),
                      key=lambda a: a.sequence)

    def sketch_list(self, sid: str, quiz, after=0, round_id=None) -> dict:
        """The sketches of the question's latest round, numbered as they came, from number
        `after` + 1 on (the presenter window's gallery asks for the new ones)."""
        s = self.session(sid)
        r = self._sketch_round(s, quiz)
        after = after if isinstance(after, int) and not isinstance(after, bool) and after > 0 else 0
        if round_id is not None and (r is None or round_id != r.id):
            after = 0                                   # a new practice round: a full snapshot
        visible = self._sketches(s, r)
        found = [{"n": a.sequence, "player": a.player, "strokes": a.payload["strokes"]}
                 for a in visible if a.sequence > after]
        return {"quiz": quiz, "round": r.id if r else None, "sketches": found,
                "cursor": max((a.sequence for a in r.answers.values()), default=0) if r else 0,
                "active": [a.player for a in visible]}

    def _shown_players(self, s: Session, r: Round | None, players) -> list[str]:
        if (not isinstance(players, list) or len(players) > SKETCHES_SHOWN
                or not all(isinstance(p, str) for p in players) or len(set(players)) != len(players)
                or any(r is None or p not in r.answers or s.players[p].kicked for p in players)):
            raise GameError("invalid", f"up to {SKETCHES_SHOWN} sketches of the question")
        return list(players)

    def sketch_show(self, sid: str, quiz, players, now: int):
        """The projector shows these sketches - players' of the question's latest round - instead
        of the slide; none: the slide again."""
        s = self.session(sid)
        before = self._shows(s, self.bundle(s))
        if not players:
            s.stage.pop("sketches", None)
        else:
            shown = self._shown_players(s, self._sketch_round(s, quiz), players)
            s.stage["sketches"] = {"quiz": quiz, "players": shown}
            s.stage.pop("poll", None)
        self._types_shown(s, self.bundle(s), before, self._shows(s, self.bundle(s)), now)
        s.last_active = now
        self._save(s)
        self._commit()

    def sketch_get(self, sid: str, quiz, players) -> dict:
        """These players' sketches, with their numbers (what the projector shows)."""
        s = self.session(sid)
        r = self._sketch_round(s, quiz)
        wanted = set(self._shown_players(s, r, players))
        return {"quiz": quiz, "sketches": [{"n": a.sequence, "player": a.player, "strokes": a.payload["strokes"]}
                                          for a in self._sketches(s, r) if a.player in wanted]}

    # ------------------------------------------------------------ questions from the audience (texstage M6, qa.py)
    def qa_open(self, sid: str, on, now: int):
        """Whether the phones may ask questions now."""
        s = self.session(sid)
        s.stage["qa"] = bool(on)
        s.last_active = now
        self._save(s)
        self._commit()

    def _asker(self, pid: str) -> tuple[Player, Session]:
        p = self.players.get(pid)
        if p is None or p.kicked:
            raise GameError("unknown-player", "please join the game again")
        return p, self.session(p.session)

    @staticmethod
    def _question(s: Session, question) -> Asked:
        q = s.questions.get(question) if isinstance(question, str) else None
        if q is None or q.state == "deleted":
            raise GameError("unknown-question", "no such question")
        return q

    def qa_ask(self, pid: str, text, now: int) -> Asked:
        p, s = self._asker(pid)
        if not s.stage.get("qa"):
            raise GameError("qa-closed", "questions are closed")
        if p.muted:
            raise GameError("qa-blocked", "the lecturer has closed questions for you")
        try:
            text = qa.clean_question(text)
        except ValueError as err:
            raise GameError("invalid", str(err)) from None
        mine = [q for q in s.questions.values() if q.player == pid]
        if mine and now - max(q.created for q in mine) < qa.GAP_MS:
            raise GameError("too-fast", f"one question every {qa.GAP_MS // 1000} seconds")
        if sum(1 for q in mine if q.state == "open") >= qa.OPEN_MAX:
            raise GameError("too-many", f"at most {qa.OPEN_MAX} open questions")
        if len(s.questions) >= qa.PER_GAME:
            raise GameError("too-many", "this game has had enough questions")
        q = Asked(secrets.token_hex(6), s.id, pid, text, now)
        s.questions[q.id] = q
        s.last_active = now
        self._save(q, s)
        self._commit()
        return q

    def qa_vote(self, pid: str, question, on, now: int) -> bool:
        """An upvote, or taken back; whether that changed anything."""
        p, s = self._asker(pid)
        q = self._question(s, question)
        if q.player == pid:
            raise GameError("qa-own", "not for your own question")
        if q.state != "open":
            raise GameError("qa-answered", "this question is answered")
        if bool(on) == (pid in q.votes):
            return False
        if on:
            q.votes.append(pid)
        else:
            q.votes.remove(pid)
        self._save(q)
        self._commit()
        return True

    def qa_show(self, sid: str, question, now: int):
        """A question on the projector, as a card over the slide; None: none."""
        s = self.session(sid)
        if question is None:
            s.stage.pop("question", None)
        else:
            s.stage["question"] = self._question(s, question).id
        s.last_active = now
        self._save(s)
        self._commit()

    def qa_mark(self, sid: str, question, state, now: int):
        """A question done (answered), deleted, or open again."""
        s = self.session(sid)
        if state not in qa.STATES:
            raise GameError("invalid", f"a question is {', '.join(qa.STATES)}")
        q = self._question(s, question)
        q.state = state
        if state != "open" and s.stage.get("question") == q.id:
            s.stage.pop("question")
        self._save(q, s)
        self._commit()

    def qa_block(self, sid: str, question, now: int):
        """Whoever asked the question asks no more; it goes, and so do their open questions."""
        s = self.session(sid)
        q = self._question(s, question)
        p = s.players.get(q.player)
        if p is not None:
            p.muted = True
            self._save(p)
        for o in s.questions.values():
            if o.player == q.player and (o.state == "open" or o is q):
                o.state = "deleted"
                self._save(o)
                if s.stage.get("question") == o.id:
                    s.stage.pop("question")
        self._save(s)
        self._commit()

    @staticmethod
    def _qa_view(s: Session, pid: str | None = None) -> list[dict]:
        """The questions as the presenter window sees them (pid None) or a phone: open ones by
        votes, then the answered ones; nobody's name."""
        out = []
        for q in qa.ranked(s.questions.values())[:100]:
            item = {"id": q.id, "text": q.text, "votes": len(q.votes), "state": q.state}
            if pid is not None:
                item["mine"], item["voted"] = q.player == pid, pid in q.votes
            out.append(item)
        return out

    # ------------------------------------------------------------ ink (texstage, ink.py)
    # Each call returns what the other windows are told ({op, ...}; None: nothing happened).
    def _ink(self, sid: str, call, *args):
        self.session(sid)
        try:
            return call(sid, *args)
        except ValueError as err:
            raise GameError("invalid", str(err)) from None

    def ink_begin(self, sid: str, device, frame, stroke, points, now: int) -> dict:
        st = self._ink(sid, self.ink.begin, device, frame, stroke, points, now)
        return {"op": "begin", "frame": st.frame, "stroke": st.view()}

    def ink_points(self, sid: str, stroke, points) -> dict:
        return {"op": "points", "stroke": stroke, "points": self._ink(sid, self.ink.extend, stroke, points)}

    def ink_end(self, sid: str, stroke, now: int) -> dict:
        st: Stroke = self._ink(sid, self.ink.end, stroke)
        self._save(st)
        self._commit()
        return {"op": "end", "frame": st.frame, "stroke": st.id}

    def ink_erase(self, sid: str, device, frame, strokes, now: int) -> dict | None:
        return self._changed("erase", self._ink(sid, self.ink.erase, device, frame, strokes, now), frame=frame)

    def ink_clear(self, sid: str, device, frame, now: int) -> dict | None:
        return self._changed("erase", self._ink(sid, self.ink.clear, device, frame, now), frame=frame)

    def ink_undo(self, sid: str, device, frame, now: int) -> dict | None:
        return self._changed(*self._ink(sid, self.ink.undo, device, frame, now), frame=frame)

    def ink_redo(self, sid: str, device, frame, now: int) -> dict | None:
        return self._changed(*self._ink(sid, self.ink.redo, device, frame, now), frame=frame)

    def ink_all(self, sid: str) -> dict:
        """All the game's ink, by frame, in the order drawn (the annotated PDF, M4)."""
        self.session(sid)
        frames: dict[str, list] = {}
        for s in self.ink.strokes.get(sid, {}).values():
            if s.erased is None:
                frames.setdefault(s.frame, []).append(s.view())
        return {"frames": frames}

    def ink_load(self, sid: str, frame) -> dict:
        """The frame's strokes, and those being drawn."""
        frame = self._ink(sid, lambda _sid, f: check_frame(f), frame)
        return {"frame": frame, "strokes": [s.view() for s in self.ink.frame(sid, frame)],
                "drawing": [s.view() for s in self.ink.drawing(sid, frame)]}

    def _changed(self, op: str, strokes: list, frame: str) -> dict | None:
        if not strokes:
            return None
        self._save(*strokes)
        self._commit()
        if op == "erase":
            return {"op": "erase", "frame": frame, "strokes": [s.id for s in strokes]}
        return {"op": "restore", "frame": frame, "strokes": [s.view() for s in strokes]}

    # ------------------------------------------------------------ time
    def tick(self, now: int) -> list[str]:
        """Apply due phase changes; the sessions that changed."""
        changed = [s.id for s in self.sessions.values() if self._advance(s, now)]
        self._commit()
        return changed

    def next_deadline(self) -> int | None:
        times = [r.opens if r.phase == "get-ready" else r.deadline
                 for s in self.sessions.values() for r in s.rounds.values()
                 if r.phase in ("get-ready", "open") and not (r.phase == "open" and r.deadline is None)]
        times += [r.closed + self.settings.grace_ms for s in self.sessions.values() for r in s.rounds.values()
                  if r.phase == "closed" and self._auto(s, r)]          # a poll's results, after the grace
        return min(times, default=None)

    # ------------------------------------------------------------ views
    def _results(self, s: Session, q: QuizDef, r: Round) -> dict:
        answers = [a for pid, a in r.answers.items() if not s.players[pid].kicked]
        res: dict = {"answered": len(answers)}
        revealed = r.phase == "revealed"
        if q.type in CHOICE_TYPES:
            counts = dict.fromkeys(q.ids, 0)
            for a in answers:
                for c in a.payload.get("choices") or [a.payload["choice"]]:
                    counts[c] += 1
            res["counts"] = counts
        elif q.type == "numeric":
            res["values"] = sorted(a.payload["value"] for a in answers)
        elif q.type in ("text", "open"):
            groups, spelling = Counter(), {}
            for a in answers:
                key = normalize_text(a.payload["text"])
                groups[key] += 1
                spelling.setdefault(key, a.payload["text"])
            res["groups"] = [{"text": spelling[k], "count": n} for k, n in groups.most_common(50)]
            if revealed and q.type == "text":
                accepted = {normalize_text(t) for t in q.keys.get("accept", [])}
                for g in res["groups"]:
                    g["correct"] = normalize_text(g["text"]) in accepted
        elif q.type == "order":
            positions = {i: [0] * len(q.ids) for i in q.ids}
            for a in answers:
                for pos, item in enumerate(a.payload["order"]):
                    positions[item][pos] += 1
            res["positions"] = positions
        if revealed and q.type not in ("poll", "open") and any(a.correct is not None for a in answers):
            res["correct"] = sum(1 for a in answers if a.correct)
        return res

    @staticmethod
    def _timing(r: Round, now: int) -> dict:
        if r.phase == "get-ready":
            remaining = r.limit_ms
        elif r.phase == "open":
            remaining = r.paused_left if r.paused_left is not None else max(0, r.deadline - now)
        else:
            remaining = 0
        return {"id": r.id, "quiz": r.quiz, "attempt": r.attempt, "practice": r.practice, "phase": r.phase,
                "opens": r.opens, "deadline": r.deadline, "limit": r.limit_ms,
                "paused": r.paused_left is not None, "remaining": remaining}

    def _host_round(self, s: Session, r: Round, now: int) -> dict:
        q = self.quiz(s, r.quiz)
        view = self._timing(r, now)
        view["answered"] = sum(1 for pid in r.answers if not s.players[pid].kicked)
        # Accepted answers survive disconnects; only connected unanswered players are pending.
        # Counting players rather than sockets also keeps reconnects and extra tabs consistent.
        view["awaiting"] = sum(1 for p in s.active_players() if p.connections > 0 and p.id not in r.answers)
        if r.phase in ("closed", "revealed"):
            view["results"] = self._results(s, q, r)
            view["closed_by"] = r.closed_by              # time, skip or all: the banner's words
        if r.phase == "revealed":
            view["keys"] = q.keys
        return view

    def _standings(self, s: Session) -> list[Player]:
        return sorted(s.active_players(), key=lambda p: (p.rank or 10**9, p.joined))

    def host_view(self, sid: str, now: int) -> dict:
        s = self.session(sid)
        if self._advance(s, now):
            self._commit()
        b = self.bundle(s)
        latest = {}
        for quiz in {r.quiz for r in s.rounds.values()}:
            latest[quiz] = self._host_round(s, s.latest(quiz), now)
        players = self._standings(s)
        return {
            "session": {"id": s.id, "pin": s.pin, "deck": s.deck, "name": b.name, "bundle": s.bundle,
                        "language": b.language,
                        "base": f"/bundle/{s.bundle}/", "slide": s.slide, "finished": s.finished is not None,
                        "current": s.rounds[s.current].quiz if s.current else None,
                        "preparing": self._preparing(s, now),
                        "players": len(players), "connected": sum(1 for p in players if p.connections)},
            "players": [{"id": p.id, "nickname": p.nickname, "score": p.score, "rank": p.rank,
                         "prev_rank": p.prev_rank, "connected": p.connections > 0} for p in players],
            "rounds": latest,
            "stage": self._stage_view(s),
            "polls": {quiz: entry["public"] for quiz, entry in s.polls.items()},
            "qa": {"open": bool(s.stage.get("qa")), "questions": self._qa_view(s)},
        }

    def results_table(self, sid: str) -> list[list]:
        """The game as a table (the host's CSV export): a row per player in rank order; per
        quiz - the deck's, then the game's polls - the answer, whether it was correct and the
        points (first, non-practice round)."""
        s = self.session(sid)
        quizzes = self.quizzes(s)
        header = ["rank", "nickname", "score", "correct", "answered"]
        for q in quizzes:
            header += [f"{q} answer", f"{q} correct", f"{q} points"]
        rounds = {q: next((r for r in sorted(s.rounds.values(), key=lambda r: r.attempt)
                           if r.quiz == q and not r.practice), None) for q in quizzes}
        rows = [header]
        for p in self._standings(s):
            cells, correct, answered = [], 0, 0
            for q in quizzes:
                a = rounds[q].answers.get(p.id) if rounds[q] else None
                if a is None:
                    cells += ["", "", ""]
                    continue
                answered += 1
                correct += bool(a.correct)
                given = a.payload
                text = given.get("choice") or " ".join(given.get("choices") or given.get("order") or []) \
                    or (str(given["value"]) if "value" in given else "(sketch)" if "strokes" in given
                        else given.get("text", ""))
                revealed = rounds[q].phase == "revealed"
                cells += [text, "" if not revealed or a.correct is None else int(a.correct),
                          a.points + a.bonus if revealed else ""]
            rows.append([p.rank or "", p.nickname, p.score, correct, answered] + cells)
        return rows

    def polls_table(self, sid: str) -> list[list]:
        """The game's polls for the lecture archive: what was asked and what came out."""
        s = self.session(sid)
        rows = [["poll", "kind", "question", "answers", "answered", "results"]]
        for quiz, entry in s.polls.items():
            public, r = entry["public"], s.latest(quiz)
            res = self._results(s, self.quiz(s, quiz), r) if r else {}
            answers = " | ".join(f"{a['id']}: {a['text']}" if a["text"] else a["id"] for a in public.get("answers", []))
            if "counts" in res:
                summary = " · ".join(f"{k} {n}" for k, n in res["counts"].items())
            elif "groups" in res:
                summary = " · ".join(f"{g['text']} ({g['count']})" for g in res["groups"][:20])
            else:
                summary = ""
            rows.append([quiz, public.get("adhoc", ""), (public.get("prompt") or {}).get("text", ""), answers,
                         res.get("answered", 0), summary])
        return rows

    def questions_table(self, sid: str) -> list[list]:
        """The audience's questions for the lecture archive, by votes (not the deleted ones)."""
        s = self.session(sid)
        return [["question", "votes", "state", "asked"]] + [
            [q.text, len(q.votes), q.state, q.created] for q in qa.ranked(s.questions.values())]

    def sketch_answers(self, sid: str) -> list[tuple[str, int, list]]:
        """Every sketch of the game - (question, number, strokes) - for the lecture archive."""
        s = self.session(sid)
        return [(quiz, a.sequence, a.payload["strokes"])
                for quiz in self.quizzes(s) if self.quiz(s, quiz).type == "sketch"
                for a in self._sketches(s, s.latest(quiz))]

    def player_view(self, pid: str, now: int, questions: bool = False) -> dict:
        """What a phone shows; with `questions` the audience's questions too (the phone has its
        questions open)."""
        p = self.players.get(pid)
        if p is None:
            raise GameError("no-session", "this game is over")
        s = self.session(p.session)
        if self._advance(s, now):
            self._commit()
        b = self.bundle(s)
        view = {
            "session": {"pin": s.pin, "name": b.name, "base": f"/bundle/{s.bundle}/",
                        "language": b.language,                       # what the phone speaks (play.js)
                        "finished": s.finished is not None},
            "me": {"id": p.id, "nickname": p.nickname, "score": p.score, "rank": p.rank,
                   "players": len(s.active_players()), "streak": p.streak},
            "round": None,
            "qa": {"open": bool(s.stage.get("qa")) and not p.muted},
        }
        if questions and view["qa"]["open"]:
            view["qa"]["questions"] = self._qa_view(s, pid)
        r = s.rounds.get(s.current or "")
        if r is not None:
            q = self.quiz(s, r.quiz)
            rv = self._timing(r, now)
            rv["question"] = q.public
            a = r.answers.get(pid)
            rv["answer"] = a.payload if a else None
            if r.phase == "revealed":
                rv["result"] = {"correct": a.correct if a else (False if q.scored or q.keys.get("correct") else None),
                                "credit": a.credit if a else 0.0, "points": a.points if a else 0,
                                "bonus": a.bonus if a else 0}
                rv["keys"] = {k: v for k, v in q.keys.items() if k in PLAYER_KEYS}
            view["round"] = rv
        else:
            info = b.slides.get(s.slide) if s.slide is not None else None
            if info is not None and info.phase == "read" and not self._preparing(s, now):
                # a reading slide is shown: its question, without the answers
                q = self.quiz(s, info.quiz)
                view["reading"] = {"quiz": info.quiz, "prompt": q.public.get("prompt")}
        if s.finished is not None:
            view["standings"] = [{"nickname": o.nickname, "score": o.score, "rank": o.rank}
                                 for o in self._standings(s)[:3] if o.rank]
        for name, kind in stage_types.TYPES.items():          # a content type's part (types.py)
            if hasattr(kind, "player_view"):
                part = kind.player_view(self._call(s, kind, now, role="player", player=p))
                if part is not None:
                    view[name] = part
        return view
