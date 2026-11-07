# SPDX-License-Identifier: Apache-2.0
"""Idempotent game-score projection of the plugin runtime's durable ledger."""
from dataclasses import dataclass, field
import copy


@dataclass
class ActivityPoints:
    session: str
    kind: str
    item: str
    epoch: int
    revision: int
    published: bool
    maximum: int
    awards: dict = field(default_factory=dict)


def reconcile(engine, snapshot):
    """Replace an absolute contribution, never increment for a delivery retry."""
    from .game import GameError
    row = ActivityPoints(**copy.deepcopy(snapshot))
    if (type(row.epoch) is not int or row.epoch < 1 or type(row.revision) is not int or row.revision < 0
            or type(row.published) is not bool or type(row.maximum) is not int or not 0 <= row.maximum <= 10000
            or type(row.awards) is not dict or len(row.awards)>1000 or (not row.published and row.awards)):
        raise GameError("activity-points", "invalid activity points snapshot")
    for actor, award in row.awards.items():
        if (not isinstance(actor,str) or not 1 <= len(actor) <= 256 or type(award) is not dict
                or set(award)!={"credit","points"} or type(award["points"]) is not int):
            raise GameError("activity-points", "invalid activity points entry")
        credit=award["credit"]
        if (credit is not None and (type(credit) is not int or not 0 <= credit <= 1000)
                or award["points"] != ((row.maximum*credit+500)//1000 if credit is not None else 0)):
            raise GameError("activity-points", "invalid activity credit")
    session=engine.session(row.session)
    key=(row.kind,row.item)
    old=session.activity_points.get(key)
    if old and (row.epoch,row.revision)<=(old.epoch,old.revision):
        if (row.epoch,row.revision)==(old.epoch,old.revision) and row!=old:
            raise GameError("activity-points", "activity points revision changed")
        return False
    prior={p.id:(p.score,p.rank,p.prev_rank) for p in session.players.values()}
    try:
        session.activity_points[key]=row
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
        for p in session.players.values():p.score,p.rank,p.prev_rank=prior[p.id]
        raise
    return True
