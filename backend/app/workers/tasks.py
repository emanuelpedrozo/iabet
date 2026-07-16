import asyncio
from datetime import datetime, timezone
from app.workers.celery_app import celery_app
from app.core.database import SessionLocal
from app.models.entities import JobLog
from app.services.sync import DataSyncService
async def log(job,status,detail):
    async with SessionLocal() as s: s.add(JobLog(job=job,status=status,detail=detail)); await s.commit()
@celery_app.task(name="app.workers.tasks.refresh_odds")
def refresh_odds():
    async def run():
        async with SessionLocal() as s: result=await DataSyncService(s).sync_odds()
        await log("refresh_odds","success",result); return result
    return asyncio.run(run())
@celery_app.task(name="app.workers.tasks.refresh_all")
def refresh_all():
    async def run():
        async with SessionLocal() as s:
            fixtures=await DataSyncService(s).sync_fixtures(); odds=await DataSyncService(s).sync_odds()
        result={"fixtures":fixtures,"odds":odds}; await log("refresh_all","success",result); return result
    return asyncio.run(run())
@celery_app.task(name="app.workers.tasks.import_api_futebol_history")
def import_api_futebol_history():
    async def run():
        async with SessionLocal() as s: result=await DataSyncService(s).import_api_futebol_history(80)
        await log("import_api_futebol_history","success",result); return result
    return asyncio.run(run())
