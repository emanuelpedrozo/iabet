from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import current_user
from app.core.database import get_session
from app.repositories.matches import MatchRepository
from app.services.models import ModelInput, ensemble
from app.services.value import evaluate, market_probability
router=APIRouter(prefix="/matches",tags=["Partidas"])

def prediction_for(m):
    if m.predictions: return sorted(m.predictions,key=lambda x:x.created_at)[-1].probabilities
    return ensemble(ModelInput(m.home_team.attack_strength,m.home_team.defense_strength,m.away_team.attack_strength,m.away_team.defense_strength,m.home_team.elo,m.away_team.elo))
def values_for(m,pred):
    latest={}
    for o in sorted(m.odds,key=lambda x:x.captured_at): latest[(o.bookmaker,o.market,o.selection)]=o
    out=[]
    for o in latest.values():
        p=market_probability(pred,o.market,o.selection)
        if p is not None:
            item=evaluate(o.market,o.selection,o.price,p,o.bookmaker)
            if item["is_value"]: out.append(item)
    return sorted(out,key=lambda x:x["expected_roi"],reverse=True)
def serialize(m):
    p=prediction_for(m); vals=values_for(m,p); winner=max(("home","draw","away"),key=p.get)
    favorite=m.home_team.name if winner=="home" else m.away_team.name if winner=="away" else "Empate"
    return {"id":m.id,"kickoff":m.kickoff,"venue":m.venue,"status":m.status.value,"competition":m.competition.name,"home_team":m.home_team,"away_team":m.away_team,"favorite":favorite,"probabilities":{k:p[k] for k in ("home","draw","away")},"best_value":vals[0] if vals else None}
@router.get("")
async def list_matches(date:datetime|None=None,competition_id:int|None=None,session:AsyncSession=Depends(get_session)):
    start=date or datetime.now(timezone.utc)-timedelta(hours=3); end=(date+timedelta(days=1)) if date else start+timedelta(days=14)
    return [serialize(m) for m in await MatchRepository(session).list(start,end,competition_id)]
@router.get("/{match_id}")
async def match_analysis(match_id:int,session:AsyncSession=Depends(get_session)):
    m=await MatchRepository(session).get(match_id)
    if not m: raise HTTPException(404,"Partida não encontrada")
    p=prediction_for(m); odds=[{"bookmaker":o.bookmaker,"market":o.market,"selection":o.selection,"line":o.line,"price":o.price,"captured_at":o.captured_at} for o in sorted(m.odds,key=lambda x:x.captured_at,reverse=True)]
    return {"match":serialize(m),"prediction":p,"odds":odds,"value_bets":values_for(m,p),"comparison":{"elo":{"home":m.home_team.elo,"away":m.away_team.elo},"attack":{"home":m.home_team.attack_strength,"away":m.away_team.attack_strength},"defense":{"home":m.home_team.defense_strength,"away":m.away_team.defense_strength}},"h2h":m.metadata_.get("h2h",[]),"players":m.metadata_.get("players",{}),"generated_at":datetime.now(timezone.utc)}
