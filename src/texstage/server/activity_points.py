# SPDX-License-Identifier: Apache-2.0
"""Durable activity contributions and the shared quiz/activity scoring timeline."""
from dataclasses import dataclass, field
import copy
from texstage.plugins.points import base_points
from .scoring import streak_bonus


@dataclass
class ActivityPoints:
    session: str
    kind: str
    item: str
    epoch: int
    revision: int
    published: bool
    maximum: int
    awards: dict = field(default_factory=dict)  # immutable source credits/times
    policy: str = "fixed-v1"
    revealed: int | None = None
    limit_ms: int = 0
    results: dict = field(default_factory=dict)  # derived from the shared timeline


def same_source(a, b):
    return all(getattr(a,k)==getattr(b,k) for k in a.__dataclass_fields__ if k != "results")


def scoring_context(session, kind, item, actor):
    row = session.activity_points.get((kind,item))
    if row is None or not row.published:
        return None
    if row.policy == "quiz-v1":
        result = row.results.get(actor)
        return {"maximum":row.maximum,"released":True,"awarded":result["points"] if result else None,
                **({k:result[k] for k in ("base_points","bonus","answer_ms","streak")} if result else {})}
    award = row.awards.get(actor)
    return {"maximum":row.maximum,"released":True,
            "awarded":award["points"] if award and award["credit"] is not None else None}


def rescore(engine, session):
    """Replay in reveal order so late feedback/reset also corrects later bonuses.

    Pending/unavailable submissions are neutral until a verified result arrives.
    Missing submissions and verified non-perfect answers break the streak, as
    in quizzes. Fixed-policy activities contribute points without touching it.
    """
    players = session.active_players()
    for p in players:
        p.score = p.streak = p.total_ms = p.rank = p.prev_rank = 0
    events = [(r.revealed or 0, 0, r.started, r.id, r) for r in session.rounds.values()
              if r.phase == "revealed" and not r.practice and engine.quiz(session,r.quiz).scored]
    for a in session.activity_points.values():
        a.results = {}
        if a.published and a.policy == "quiz-v1":
            events.append((a.revealed,1,0,a.kind+"/"+a.item,a))
    def rank():
        for i,p in enumerate(sorted(players,key=lambda p:(-p.score,p.total_ms,p.joined)),1):
            p.prev_rank,p.rank = p.rank,i
    for _,kind,_,_,row in sorted(events,key=lambda e:e[:4]):
        for p in players:
            if kind == 0:
                answer = row.answers.get(p.id)
                p.streak = p.streak+1 if answer is not None and answer.correct else 0
                if answer is not None:
                    answer.bonus = streak_bonus(p.streak) if engine.settings.streak_bonus else 0
                    p.score += answer.points+answer.bonus
                    p.total_ms += answer.answer_ms
            else:
                award = row.awards.get(p.id)
                if award is None:
                    p.streak = 0
                elif award["credit"] is not None:
                    p.streak = p.streak+1 if award["credit"] == 1000 else 0
                    bonus = streak_bonus(p.streak) if engine.settings.streak_bonus else 0
                    result = {"points":award["points"]+bonus,"base_points":award["points"],
                              "bonus":bonus,"answer_ms":award["answer_ms"],"streak":p.streak}
                    row.results[p.id] = result
                    p.score += result["points"]
                    p.total_ms += award["answer_ms"]
        rank()
    fixed = [a for a in session.activity_points.values() if a.published and a.policy == "fixed-v1"]
    if fixed:
        for p in players:
            p.score += sum(a.awards.get(p.id,{}).get("points",0) for a in fixed)
        rank()
    # One write per final row, not one write per historical event/player pair.
    for p in players:engine._save(p)
    for r in session.rounds.values():
        for answer in r.answers.values():engine._save(answer)
    for a in session.activity_points.values():engine._save(a)


def reconcile(engine, snapshot):
    """Replace an absolute contribution; delivery retries never increment it."""
    from .game import GameError
    if "results" in snapshot:
        raise GameError("activity-points", "computed activity points are host-owned")
    row = ActivityPoints(**copy.deepcopy(snapshot))
    if (type(row.epoch) is not int or row.epoch < 1 or type(row.revision) is not int or row.revision < 0
            or type(row.published) is not bool or type(row.maximum) is not int or not 0 <= row.maximum <= 10000
            or type(row.awards) is not dict or len(row.awards)>1000 or (not row.published and row.awards)
            or row.policy not in ("fixed-v1","quiz-v1")):
        raise GameError("activity-points", "invalid activity points snapshot")
    if row.policy == "quiz-v1" and (type(row.limit_ms) is not int or not 1000 <= row.limit_ms <= 3600000
            or (row.published and (type(row.revealed) is not int or row.revealed < 0))):
        raise GameError("activity-points", "invalid activity clock")
    for actor, award in row.awards.items():
        expected = {"credit","points","answer_ms"} if row.policy == "quiz-v1" else {"credit","points"}
        if (not isinstance(actor,str) or not 1 <= len(actor) <= 256 or type(award) is not dict
                or set(award)!=expected or type(award["points"]) is not int):
            raise GameError("activity-points", "invalid activity points entry")
        credit, elapsed = award["credit"], award.get("answer_ms",0)
        if row.policy == "quiz-v1" and (type(elapsed) is not int or not 0 <= elapsed <= row.limit_ms):
            raise GameError("activity-points", "invalid activity answer time")
        if (credit is not None and (type(credit) is not int or not 0 <= credit <= 1000)
                or award["points"] != base_points(row.maximum,credit,row.policy,elapsed,row.limit_ms)):
            raise GameError("activity-points", "invalid activity credit")
    session=engine.session(row.session)
    key=(row.kind,row.item)
    old=session.activity_points.get(key)
    if old and (row.epoch,row.revision)<=(old.epoch,old.revision):
        if (row.epoch,row.revision)==(old.epoch,old.revision) and not same_source(row,old):
            raise GameError("activity-points", "activity points revision changed")
        return False
    # After reset the mirror remains present. Private clock/credit revisions
    # must not replay the shared timeline or broadcast every player's score.
    # Keep the durable projection revision current without touching class
    # totals/ranks for private attempts under either scoring policy.
    if not row.published and not (old and old.published):
        try:
            engine._save(row)
            engine._commit()
        except Exception:
            if engine.store is not None:engine.store.db.rollback()
            raise
        session.activity_points[key]=row
        return False
    prior={p.id:(p.score,p.streak,p.total_ms,p.rank,p.prev_rank) for p in session.players.values()}
    answers=[(a,a.bonus) for r in session.rounds.values() for a in r.answers.values()]
    results={k:copy.deepcopy(a.results) for k,a in session.activity_points.items()}
    try:
        session.activity_points[key]=row
        if any(a.policy == "quiz-v1" for a in session.activity_points.values()):
            rescore(engine,session)
        else:
            for p in session.players.values():
                before=old.awards.get(p.id,{}).get("points",0) if old else 0
                after=row.awards.get(p.id,{}).get("points",0)
                p.score+=after-before
                if after!=before:engine._save(p)
            engine._save(row)
            scored=any(a.published for a in session.activity_points.values()) or any(
                r.phase=="revealed" and not r.practice and engine.quiz(session,r.quiz).scored for r in session.rounds.values())
            if scored:
                engine._rank(session)
            else:
                for p in session.active_players():
                    p.rank=p.prev_rank=0;engine._save(p)
        engine._commit()
    except Exception:
        if engine.store is not None:engine.store.db.rollback()
        if old is None:session.activity_points.pop(key,None)
        else:session.activity_points[key]=old
        for p in session.players.values():p.score,p.streak,p.total_ms,p.rank,p.prev_rank=prior[p.id]
        for answer,bonus in answers:answer.bonus=bonus
        for k,value in results.items():session.activity_points[k].results=value
        raise
    return True
