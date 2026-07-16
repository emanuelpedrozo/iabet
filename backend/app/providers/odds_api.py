from datetime import datetime
import httpx
from app.core.config import settings
from app.providers.base import OddsProvider
class OddsApiProvider(OddsProvider):
    name="odds_api"
    async def odds(self,external_ids:list[str])->list[dict]:
        if not settings.odds_api_key: return []
        async with httpx.AsyncClient(timeout=20) as client:
            response=await client.get("https://api.the-odds-api.com/v4/sports/soccer_brazil_campeonato/odds",params={"apiKey":settings.odds_api_key,"regions":"eu","markets":"h2h,totals","oddsFormat":"decimal"})
            response.raise_for_status(); return response.json()

    async def usage(self)->dict:
        if not settings.odds_api_key: return {"configured":False}
        async with httpx.AsyncClient(timeout=20) as client:
            response=await client.get("https://api.the-odds-api.com/v4/sports",params={"apiKey":settings.odds_api_key})
            response.raise_for_status()
            return {"configured":True,"remaining":response.headers.get("x-requests-remaining"),"used":response.headers.get("x-requests-used")}
