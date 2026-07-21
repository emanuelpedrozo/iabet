import asyncio
import traceback
from app.workers.celery_app import celery_app
from app.core.database import SessionLocal, engine
from app.models.entities import JobLog
from app.services.sync import DataSyncService
from app.services.ml_history import MlHistoryService
from app.services.ml_training import MlTrainingService
from app.services.ml_shadow import MlShadowService


async def log(job: str, status: str, detail: dict):
    async with SessionLocal() as s:
        s.add(JobLog(job=job, status=status, detail=detail))
        await s.commit()


async def _run_logged(job: str, coro_factory):
    try:
        result = await coro_factory()
        await log(job, "success", result if isinstance(result, dict) else {"result": result})
        return result
    except Exception as exc:
        await log(
            job,
            "failure",
            {
                "error": str(exc)[:500],
                "traceback": traceback.format_exc()[:2000],
            },
        )
        raise


def _run(job: str, coro_factory):
    """Run one Celery job without reusing asyncpg connections across event loops."""
    async def runner():
        try:
            return await _run_logged(job, coro_factory)
        finally:
            # Celery reuses the same process, while asyncio.run creates a new loop
            # for every task. Pooled asyncpg connections belong to the old loop.
            await engine.dispose()

    return asyncio.run(runner())


@celery_app.task(name="app.workers.tasks.refresh_odds")
def refresh_odds():
    async def work():
        async with SessionLocal() as s:
            return await DataSyncService(s).sync_odds()

    return _run("refresh_odds", work)


@celery_app.task(name="app.workers.tasks.refresh_all")
def refresh_all():
    async def work():
        async with SessionLocal() as s:
            service = DataSyncService(s)
            fixtures = await service.sync_fixtures()
            odds = await service.sync_odds()
            # sync_fixtures já materializa predições; reforça após odds
            predictions = await service.refresh_predictions()
            return {"fixtures": fixtures, "odds": odds, "predictions": predictions}

    return _run("refresh_all", work)


@celery_app.task(name="app.workers.tasks.import_api_futebol_history")
def import_api_futebol_history():
    async def work():
        async with SessionLocal() as s:
            return await DataSyncService(s).import_api_futebol_history(80)

    return _run("import_api_futebol_history", work)


@celery_app.task(name="app.workers.tasks.sync_today_matches")
def sync_today_matches():
    async def work():
        async with SessionLocal() as s:
            return await DataSyncService(s).sync_today_matches()

    return _run("sync_today_matches", work)


@celery_app.task(name="app.workers.tasks.sync_bzzoiro_today")
def sync_bzzoiro_today():
    async def work():
        async with SessionLocal() as s:
            return await DataSyncService(s).sync_bzzoiro_today()

    return _run("sync_bzzoiro_today", work)


@celery_app.task(name="app.workers.tasks.import_cartola_recent")
def import_cartola_recent():
    async def work():
        async with SessionLocal() as s:
            return await DataSyncService(s).import_cartola_recent(10)

    return _run("import_cartola_recent", work)


@celery_app.task(name="app.workers.tasks.refresh_predictions")
def refresh_predictions():
    async def work():
        async with SessionLocal() as s:
            return await DataSyncService(s).refresh_predictions()

    return _run("refresh_predictions", work)


@celery_app.task(name="app.workers.tasks.import_bzzoiro_ml_history")
def import_bzzoiro_ml_history(year: int, include_details: bool = False):
    async def work():
        async with SessionLocal() as s:
            return await MlHistoryService(s).import_bzzoiro_serie_a(year, include_details)

    return _run(f"import_bzzoiro_ml_history_{year}", work)


@celery_app.task(name="app.workers.tasks.import_football_data_ml_history")
def import_football_data_ml_history(year: int):
    async def work():
        async with SessionLocal() as s:
            return await MlHistoryService(s).import_football_data_serie_a(year)

    return _run(f"import_football_data_ml_history_{year}", work)


@celery_app.task(name="app.workers.tasks.train_ml_result_baseline")
def train_ml_result_baseline():
    async def work():
        async with SessionLocal() as s:
            training = await MlTrainingService(s).train_result_baseline()
            # Uma nova versão passa a ser a mais recente imediatamente. Materialize
            # suas previsões no mesmo job para o painel nunca ficar vazio entre o
            # treinamento e a próxima execução periódica do modo sombra.
            shadow = await MlShadowService(s).materialize()
            return {**training, "shadow": shadow}

    return _run("train_ml_result_baseline", work)


@celery_app.task(name="app.workers.tasks.materialize_ml_shadow")
def materialize_ml_shadow():
    async def work():
        async with SessionLocal() as s:
            return await MlShadowService(s).materialize()

    return _run("materialize_ml_shadow", work)


@celery_app.task(name="app.workers.tasks.import_api_sports_history")
def import_api_sports_history():
    async def work():
        async with SessionLocal() as s:
            service = DataSyncService(s)
            serie_a = await service.import_api_sports_history(2024, 38, "A")
            serie_b = await service.import_api_sports_history(2024, 38, "B")
            return {"serie_a": serie_a, "serie_b": serie_b}

    return _run("import_api_sports_history", work)
