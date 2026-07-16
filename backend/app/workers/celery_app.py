from celery import Celery
from celery.schedules import crontab
from app.core.config import settings
celery_app=Celery("iabet",broker=settings.redis_url,backend=settings.redis_url,include=["app.workers.tasks"])
celery_app.conf.update(timezone="America/Sao_Paulo",task_track_started=True,beat_schedule={
 "fixtures-daily":{"task":"app.workers.tasks.refresh_all","schedule":crontab(hour=5,minute=0)},
 "history-daily":{"task":"app.workers.tasks.import_api_futebol_history","schedule":crontab(hour=6,minute=15)},
 "api-sports-history-daily":{"task":"app.workers.tasks.import_api_sports_history","schedule":crontab(hour=6,minute=45)},
 "odds-frequent":{"task":"app.workers.tasks.refresh_odds","schedule":crontab(minute="*/15")},
})
