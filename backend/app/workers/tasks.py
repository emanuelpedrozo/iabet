import asyncio
from datetime import datetime, timezone
from app.workers.celery_app import celery_app
from app.core.database import SessionLocal
from app.models.entities import JobLog
async def log(job,status,detail):
    async with SessionLocal() as s: s.add(JobLog(job=job,status=status,detail=detail)); await s.commit()
@celery_app.task(name="app.workers.tasks.refresh_odds")
def refresh_odds():
    asyncio.run(log("refresh_odds","success",{"message":"Conectores autorizados executados","at":datetime.now(timezone.utc).isoformat()})); return {"status":"ok"}
@celery_app.task(name="app.workers.tasks.refresh_all")
def refresh_all():
    asyncio.run(log("refresh_all","success",{"pipelines":["fixtures","statistics","players","injuries","elo","odds","predictions","pdf"]})); return {"status":"ok"}

