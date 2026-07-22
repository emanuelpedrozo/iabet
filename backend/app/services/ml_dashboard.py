from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ml_entities import MlModelRun
from app.services.ml_history import MlHistoryService
from app.services.ml_shadow import MlShadowService


async def ml_dashboard_overview(session: AsyncSession) -> dict:
    """Monta os dados públicos de leitura sem expor operações administrativas."""
    result = await MlHistoryService(session).overview()
    runs = list(
        await session.scalars(
            select(MlModelRun).order_by(MlModelRun.created_at.desc()).limit(5)
        )
    )
    result["model_runs"] = [
        {
            "version": run.version,
            "algorithm": run.algorithm,
            "status": run.status,
            "train_seasons": run.train_seasons,
            "test_season": run.test_season,
            "train_samples": run.train_samples,
            "test_samples": run.test_samples,
            "metrics": run.metrics,
            "created_at": run.created_at,
        }
        for run in runs
    ]
    result["shadow"] = await MlShadowService(session).overview()
    return result
