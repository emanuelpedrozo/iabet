from celery import Celery
from celery.schedules import crontab
from app.core.config import settings
celery_app=Celery("iabet",broker=settings.redis_url,backend=settings.redis_url,include=["app.workers.tasks"])
celery_app.conf.update(timezone="America/Sao_Paulo",task_track_started=True,beat_schedule={
 "fixtures-daily":{"task":"app.workers.tasks.refresh_all","schedule":crontab(hour=5,minute=0)},
 # Jogos do dia apenas; o serviço aplica throttle de 3h pré-jogo e 1h pós-início.
 "today-matches":{"task":"app.workers.tasks.sync_today_matches","schedule":crontab(hour="10-23",minute=0)},
 "cartola-recent":{"task":"app.workers.tasks.import_cartola_recent","schedule":crontab(hour=4,minute=15)},
 "odds-frequent":{"task":"app.workers.tasks.refresh_odds","schedule":crontab(minute="*/15")},
 # A API retorna provável antes do jogo e oficial perto do início.
 "bzzoiro-lineups":{"task":"app.workers.tasks.sync_bzzoiro_today","schedule":crontab(minute="*/15")},
 "ml-shadow":{"task":"app.workers.tasks.materialize_ml_shadow","schedule":crontab(minute="*/30")},
})
