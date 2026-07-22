from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.services.ml_dashboard import ml_dashboard_overview

router = APIRouter(prefix="/ml", tags=["Machine Learning"])


@router.get("/overview")
async def overview(session: AsyncSession = Depends(get_session)):
    return await ml_dashboard_overview(session)
