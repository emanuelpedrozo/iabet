from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import admin
from app.core.database import get_session
from app.models.entities import JobLog, Match, Team, User
from app.workers.tasks import refresh_all
router=APIRouter(prefix="/admin",tags=["Admin"],dependencies=[Depends(admin)])
@router.get("/overview")
async def overview(session:AsyncSession=Depends(get_session)):
    async def count(model): return await session.scalar(select(func.count()).select_from(model))
    logs=list(await session.scalars(select(JobLog).order_by(JobLog.created_at.desc()).limit(20)))
    return {"users":await count(User),"teams":await count(Team),"matches":await count(Match),"logs":[{"job":x.job,"status":x.status,"detail":x.detail,"created_at":x.created_at} for x in logs]}
@router.post("/refresh")
async def refresh():
    task=refresh_all.delay(); return {"task_id":task.id,"status":"queued"}

