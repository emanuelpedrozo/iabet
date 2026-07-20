from datetime import datetime, timedelta, timezone
from hashlib import sha256
from secrets import token_urlsafe

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import admin
from app.core.database import get_session
from app.models.entities import Invitation, JobLog, Match, PlayerMatchStat, Team, User
from app.models.ml_entities import MlModelRun
from app.workers.tasks import (
    import_bzzoiro_ml_history,
    import_football_data_ml_history,
    materialize_ml_shadow,
    refresh_all,
    train_ml_result_baseline,
)
from app.providers.api_futebol import ApiFutebolProvider
from app.providers.football_data import FootballDataProvider
from app.providers.odds_api import OddsApiProvider
from app.providers.api_sports import ApiSportsProvider
from app.providers.cartola import CartolaProvider
from app.providers.bzzoiro import BzzoiroProvider
from app.services.sync import DataSyncService
from app.services.ml_history import MlHistoryService
from app.services.ml_shadow import MlShadowService

router = APIRouter(prefix="/admin", tags=["Admin"], dependencies=[Depends(admin)])


class UserAccessUpdate(BaseModel):
    active: bool | None = None
    role: str | None = None


class InviteCreate(BaseModel):
    role: str = "user"
    expires_hours: int = 72


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
        "pending_users": await session.scalar(
            select(func.count()).select_from(User).where(User.active.is_(False))
        ),
        "teams": await count(Team),
        "matches": await count(Match),
        "player_match_stats": await count(PlayerMatchStat),
        "logs": [
            {"job": x.job, "status": x.status, "detail": x.detail, "created_at": x.created_at}
            for x in logs
        ],
    }


@router.get("/users")
async def list_users(session: AsyncSession = Depends(get_session)):
    users = list(await session.scalars(select(User).order_by(User.created_at.desc())))
    return [{
        "id": user.id, "email": user.email, "role": user.role,
        "active": user.active, "created_at": user.created_at,
    } for user in users]


@router.patch("/users/{user_id}")
async def update_user_access(
    user_id: int,
    data: UserAccessUpdate,
    actor: User = Depends(admin),
    session: AsyncSession = Depends(get_session),
):
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(404, "Usuário não encontrado")
    if user.id == actor.id and (data.active is False or data.role == "user"):
        raise HTTPException(400, "Você não pode remover o próprio acesso administrativo")
    if data.role is not None:
        if data.role not in {"user", "admin"}:
            raise HTTPException(400, "Perfil inválido")
        user.role = data.role
    if data.active is not None:
        user.active = data.active
    await session.commit()
    return {"id": user.id, "email": user.email, "role": user.role, "active": user.active}


@router.post("/invitations", status_code=201)
async def create_invitation(data: InviteCreate, session: AsyncSession = Depends(get_session)):
    if data.role not in {"user", "admin"}:
        raise HTTPException(400, "Perfil inválido")
    if not 1 <= data.expires_hours <= 720:
        raise HTTPException(400, "Validade deve ficar entre 1 e 720 horas")
    token = token_urlsafe(32)
    invitation = Invitation(
        token_hash=sha256(token.encode()).hexdigest(),
        role=data.role,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=data.expires_hours),
    )
    session.add(invitation)
    await session.commit()
    return {"invite_code": token, "role": invitation.role, "expires_at": invitation.expires_at}


@router.get("/invitations")
async def list_invitations(session: AsyncSession = Depends(get_session)):
    invitations = list(await session.scalars(
        select(Invitation).order_by(Invitation.created_at.desc()).limit(20)
    ))
    now = datetime.now(timezone.utc)
    return [{
        "id": invitation.id, "role": invitation.role,
        "expires_at": invitation.expires_at, "used_at": invitation.used_at,
        "status": "used" if invitation.used_at else "expired" if invitation.expires_at <= now else "active",
    } for invitation in invitations]


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
        await safe("api_sports", ApiSportsProvider().status),
        await safe("cartola", CartolaProvider().status),
        await safe("bzzoiro", BzzoiroProvider().status),
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


@router.post("/sync/today-matches")
async def sync_today_matches(session: AsyncSession = Depends(get_session)):
    try:
        return await DataSyncService(session).sync_today_matches()
    except ValueError as exc:
        raise _map_sync_error(exc) from exc


@router.post("/sync/bzzoiro-today")
async def sync_bzzoiro_today(session: AsyncSession = Depends(get_session)):
    try:
        return await DataSyncService(session).sync_bzzoiro_today()
    except (ValueError, RuntimeError) as exc:
        raise _map_sync_error(exc) from exc


@router.post("/ml/import-bzzoiro")
async def import_ml_history(
    year: int,
    include_details: bool = False,
    session: AsyncSession = Depends(get_session),
):
    if year < 2001 or year > datetime.now().year:
        raise HTTPException(400, "Temporada fora do intervalo disponível (2001 até o ano atual)")
    task = import_bzzoiro_ml_history.delay(year, include_details)
    session.add(JobLog(
        job=f"import_bzzoiro_ml_history_{year}",
        status="queued",
        detail={"task_id": task.id, "include_details": include_details},
    ))
    await session.commit()
    return {"task_id": task.id, "status": "queued", "year": year,
            "include_details": include_details}


@router.get("/ml/overview")
async def ml_overview(session: AsyncSession = Depends(get_session)):
    result = await MlHistoryService(session).overview()
    runs = list(await session.scalars(
        select(MlModelRun).order_by(MlModelRun.created_at.desc()).limit(5)
    ))
    result["model_runs"] = [{
        "version": run.version, "algorithm": run.algorithm,
        "status": run.status,
        "train_seasons": run.train_seasons, "test_season": run.test_season,
        "train_samples": run.train_samples, "test_samples": run.test_samples,
        "metrics": run.metrics, "created_at": run.created_at,
    } for run in runs]
    result["shadow"] = await MlShadowService(session).overview()
    return result


@router.post("/ml/import-football-data")
async def import_ml_football_data(year: int, session: AsyncSession = Depends(get_session)):
    if year < 2001 or year > datetime.now().year:
        raise HTTPException(400, "Temporada fora do intervalo disponível")
    task = import_football_data_ml_history.delay(year)
    session.add(JobLog(
        job=f"import_football_data_ml_history_{year}", status="queued",
        detail={"task_id": task.id},
    ))
    await session.commit()
    return {"task_id": task.id, "status": "queued", "year": year}


@router.post("/ml/train")
async def train_ml(session: AsyncSession = Depends(get_session)):
    task = train_ml_result_baseline.delay()
    session.add(JobLog(
        job="train_ml_result_baseline", status="queued", detail={"task_id": task.id}
    ))
    await session.commit()
    return {"task_id": task.id, "status": "queued"}


@router.post("/ml/shadow/materialize")
async def materialize_shadow(session: AsyncSession = Depends(get_session)):
    task = materialize_ml_shadow.delay()
    session.add(JobLog(
        job="materialize_ml_shadow", status="queued", detail={"task_id": task.id}
    ))
    await session.commit()
    return {"task_id": task.id, "status": "queued"}


@router.post("/sync/cartola-recent")
async def sync_cartola_recent(rounds: int = 10, session: AsyncSession = Depends(get_session)):
    try:
        return await DataSyncService(session).import_cartola_recent(min(max(rounds, 1), 10))
    except (ValueError, RuntimeError) as exc:
        raise _map_sync_error(exc) from exc


@router.post("/sync/predictions")
async def sync_predictions(session: AsyncSession = Depends(get_session)):
    try:
        return await DataSyncService(session).refresh_predictions()
    except ValueError as exc:
        raise _map_sync_error(exc) from exc


@router.get("/sync/api-sports-progress")
async def api_sports_progress(
    season: int = 2024, division: str = "A", session: AsyncSession = Depends(get_session)
):
    return await DataSyncService(session).api_sports_progress(season, division)


@router.post("/sync/api-sports-history")
async def sync_api_sports_history(
    season: int = 2024,
    limit: int = 10,
    division: str = "A",
    session: AsyncSession = Depends(get_session),
):
    try:
        return await DataSyncService(session).import_api_sports_history(season, limit, division)
    except (ValueError, RuntimeError) as exc:
        raise _map_sync_error(exc) from exc
