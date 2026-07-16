from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.entities import Match
class MatchRepository:
    def __init__(self,session:AsyncSession): self.session=session
    async def list(self,date_from:datetime|None=None,date_to:datetime|None=None,competition_id:int|None=None):
        q=select(Match).options(selectinload(Match.home_team),selectinload(Match.away_team),selectinload(Match.competition),selectinload(Match.odds),selectinload(Match.predictions)).order_by(Match.kickoff)
        if date_from:q=q.where(Match.kickoff>=date_from)
        if date_to:q=q.where(Match.kickoff<=date_to)
        if competition_id:q=q.where(Match.competition_id==competition_id)
        return list((await self.session.scalars(q)).unique())
    async def get(self,match_id:int):
        q=select(Match).where(Match.id==match_id).options(selectinload(Match.home_team),selectinload(Match.away_team),selectinload(Match.competition),selectinload(Match.odds),selectinload(Match.predictions))
        return (await self.session.scalars(q)).unique().one_or_none()

