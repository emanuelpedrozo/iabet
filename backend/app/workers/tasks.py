import asyncio
import traceback
from app.workers.celery_app import celery_app
from app.core.database import SessionLocal
from app.models.entities import JobLog
from app.services.sync import DataSyncService


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


@celery_app.task(name="app.workers.tasks.refresh_odds")
def refresh_odds():
    async def work():
        async with SessionLocal() as s:
            return await DataSyncService(s).sync_odds()

    return asyncio.run(_run_logged("refresh_odds", work))


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

    return asyncio.run(_run_logged("refresh_all", work))


@celery_app.task(name="app.workers.tasks.import_api_futebol_history")
def import_api_futebol_history():
    async def work():
        async with SessionLocal() as s:
            return await DataSyncService(s).import_api_futebol_history(80)

    return asyncio.run(_run_logged("import_api_futebol_history", work))


@celery_app.task(name="app.workers.tasks.sync_today_matches")
def sync_today_matches():
    async def work():
        async with SessionLocal() as s:
            return await DataSyncService(s).sync_today_matches()

    return asyncio.run(_run_logged("sync_today_matches", work))


@celery_app.task(name="app.workers.tasks.import_cartola_recent")
def import_cartola_recent():
    async def work():
        async with SessionLocal() as s:
            return await DataSyncService(s).import_cartola_recent(10)

    return asyncio.run(_run_logged("import_cartola_recent", work))


@celery_app.task(name="app.workers.tasks.refresh_predictions")
def refresh_predictions():
    async def work():
        async with SessionLocal() as s:
            return await DataSyncService(s).refresh_predictions()

    return asyncio.run(_run_logged("refresh_predictions", work))


@celery_app.task(name="app.workers.tasks.import_api_sports_history")
def import_api_sports_history():
    async def work():
        async with SessionLocal() as s:
            service = DataSyncService(s)
            serie_a = await service.import_api_sports_history(2024, 38, "A")
            serie_b = await service.import_api_sports_history(2024, 38, "B")
            return {"serie_a": serie_a, "serie_b": serie_b}

    return asyncio.run(_run_logged("import_api_sports_history", work))
