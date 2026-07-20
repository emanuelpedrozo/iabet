import asyncio
from datetime import datetime, timezone
from sqlalchemy import select
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.entities import Competition, Match, Odd, Prediction, Team, User
from app.services.models import ModelInput, ensemble

TEAMS={
 "Botafogo":(1538,1.03,1.02),"Santos":(1514,.98,1.06),"Vitória":(1497,.94,1.03),"Vasco":(1489,.99,1.10),"Bahia":(1615,1.22,.88),"Chapecoense":(1438,.82,1.18),"Fluminense":(1602,1.15,.94),"RB Bragantino":(1574,1.10,.96),"Mirassol":(1472,.92,1.12),"Grêmio":(1490,.96,1.08)}
FIXTURES=[
 ("Botafogo","Santos","2026-07-16T22:30:00+00:00","Nilton Santos",{"home":2.08,"draw":3.46,"away":3.56}),
 ("Vitória","Vasco","2026-07-16T22:30:00+00:00","Barradão",{"home":2.34,"draw":3.30,"away":3.15}),
 ("Bahia","Chapecoense","2026-07-17T22:30:00+00:00","Arena Fonte Nova",{"home":1.48,"draw":5.00,"away":7.00}),
 ("Fluminense","RB Bragantino","2026-07-17T23:00:00+00:00","Maracanã",{"home":1.95,"draw":3.42,"away":4.15}),
 ("Mirassol","Grêmio","2026-07-17T23:00:00+00:00","José Maria de Campos Maia",{"home":2.00,"draw":3.40,"away":4.00})]

async def main():
 async with SessionLocal() as s:
  admin_email=settings.admin_email.lower().strip()
  admin=await s.scalar(select(User).where(User.email==admin_email))
  if not admin:
   s.add(User(email=admin_email,password_hash=hash_password(settings.admin_password),role="admin"))
  else:
   # O .env é a fonte de verdade do administrador de uso próprio. Isso também
   # recupera o acesso quando a senha foi alterada depois do primeiro deploy.
   # Se a pessoa acabou de se cadastrar com o e-mail administrativo, preserva
   # a senha escolhida. Administradores já existentes continuam sincronizados.
   if admin.role=="admin": admin.password_hash=hash_password(settings.admin_password)
   admin.role="admin"; admin.active=True
  comp=await s.scalar(select(Competition).where(Competition.name=="Brasileirão Série A",Competition.season=="2026"))
  if not comp: comp=Competition(name="Brasileirão Série A",country="Brasil",season="2026"); s.add(comp); await s.flush()
  dbteams={}
  for name,(elo,att,deff) in TEAMS.items():
   t=await s.scalar(select(Team).where(Team.name==name))
   if not t: t=Team(name=name,short_name=name[:3].upper(),elo=elo,attack_strength=att,defense_strength=deff); s.add(t); await s.flush()
   dbteams[name]=t
  if not await s.scalar(select(Match).limit(1)):
   now=datetime.now(timezone.utc)
   for home,away,kickoff,venue,prices in FIXTURES:
    h,a=dbteams[home],dbteams[away]; inp=ModelInput(h.attack_strength,h.defense_strength,a.attack_strength,a.defense_strength,h.elo,a.elo); pred=ensemble(inp)
    m=Match(competition_id=comp.id,home_team_id=h.id,away_team_id=a.id,kickoff=datetime.fromisoformat(kickoff),venue=venue,metadata_={"h2h":[],"players":{"home":[],"away":[]}}); s.add(m); await s.flush()
    s.add(Prediction(match_id=m.id,model_version="ensemble-1.4",probabilities=pred,expected_home_goals=pred["xg_home"],expected_away_goals=pred["xg_away"],score_mode=pred["score"],features={"seed":True}))
    for selection,price in prices.items(): s.add(Odd(match_id=m.id,bookmaker="Mercado agregado",market="match_result",selection=selection,price=price,captured_at=now))
  await s.commit()
if __name__=="__main__": asyncio.run(main())
