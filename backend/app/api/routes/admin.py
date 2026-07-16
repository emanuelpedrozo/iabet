from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import admin
from app.core.database import get_session
from app.models.entities import JobLog, Match, Team, User
from app.workers.tasks import refresh_all
from app.providers.api_futebol import ApiFutebolProvider
from app.providers.football_data import FootballDataProvider
from app.providers.odds_api import OddsApiProvider
from app.services.sync import DataSyncService

router = APIRouter(prefix="/admin", tags=["Admin"], dependencies=[Depends(admin)])


def _map_sync_error(exc: Exception) -> HTTPException:
    msg = str(exc)
    if "não encontrada" in msg.lower():
        return HTTPException(404, msg)
    if "não vinculada" in msg.lower() or "ainda não" in msg.lower():
        return HTTPException(400, msg)
    return HTTPException(400, msg)


@router.get("/overview")
async def overview(session: AsyncSession = Depends(get_session)):
    async def count(model):
        return await session.scalar(select(func.count()).select_from(model))

    logs = list(await session.scalars(select(JobLog).order_by(JobLog.created_at.desc()).limit(20)))
    return {
        "users": await count(User),
        "teams": await count(Team),
        "matches": await count(Match),
        "logs": [
            {"job": x.job, "status": x.status, "detail": x.detail, "created_at": x.created_at}
            for x in logs
        ],
    }


@router.post("/refresh")
async def refresh():
    task = refresh_all.delay()
    return {"task_id": task.id, "status": "queued"}


@router.get("/providers")
async def providers():
    async def safe(name, call):
        try:
            return {"name": name, "healthy": True, **await call()}
        except Exception as exc:
            return {"name": name, "healthy": False, "error": str(exc)[:200]}

    return [
        await safe("football_data", FootballDataProvider().usage),
        await safe("odds_api", OddsApiProvider().usage),
        await safe("api_futebol", ApiFutebolProvider().status),
    ]


@router.post("/sync/fixtures")
async def sync_fixtures(session: AsyncSession = Depends(get_session)):
    try:
        return await DataSyncService(session).sync_fixtures()
    except ValueError as exc:
        raise _map_sync_error(exc) from exc


@router.post("/sync/odds")
async def sync_odds(session: AsyncSession = Depends(get_session)):
    try:
        return await DataSyncService(session).sync_odds()
    except ValueError as exc:
        raise _map_sync_error(exc) from exc


@router.post("/sync/api-futebol-index")
async def sync_api_futebol_index(session: AsyncSession = Depends(get_session)):
    try:
        return await DataSyncService(session).sync_api_futebol_index()
    except ValueError as exc:
        raise _map_sync_error(exc) from exc


@router.post("/sync/api-futebol-match/{match_id}")
async def sync_api_futebol_match(match_id: int, session: AsyncSession = Depends(get_session)):
    try:
        return await DataSyncService(session).sync_api_futebol_match(match_id)
    except ValueError as exc:
        raise _map_sync_error(exc) from exc


@router.post("/sync/api-futebol-history")
async def sync_api_futebol_history(limit: int = 80, session: AsyncSession = Depends(get_session)):
    try:
        return await DataSyncService(session).import_api_futebol_history(limit)
    except ValueError as exc:
        raise _map_sync_error(exc) from exc


@router.post("/sync/predictions")
async def sync_predictions(session: AsyncSession = Depends(get_session)):
    try:
        return await DataSyncService(session).refresh_predictions()
    except ValueError as exc:
        raise _map_sync_error(exc) from exc
