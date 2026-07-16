from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_session
from app.repositories.matches import MatchRepository
from app.api.routes.matches import serialize, prediction_for, values_for
from app.services.report import build_pdf
router=APIRouter(prefix="/reports",tags=["Relatórios"])
@router.get("/{match_id}.pdf")
async def report(match_id:int,session:AsyncSession=Depends(get_session)):
    m=await MatchRepository(session).get(match_id)
    if not m: raise HTTPException(404,"Partida não encontrada")
    p=prediction_for(m); data={"match":serialize(m),"prediction":p,"value_bets":values_for(m,p)}
    return Response(build_pdf(data),media_type="application/pdf",headers={"Content-Disposition":f'attachment; filename="iabet-{match_id}.pdf"'})

