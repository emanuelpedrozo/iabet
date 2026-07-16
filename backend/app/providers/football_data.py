from datetime import datetime
import httpx
from app.core.config import settings

class FootballDataProvider:
    name="football_data"
    base_url="https://api.football-data.org/v4"
    def _headers(self): return {"X-Auth-Token":settings.football_data_key or ""}
    async def _get(self,path:str,params:dict|None=None):
        if not settings.football_data_key: raise RuntimeError("FOOTBALL_DATA_KEY não configurada")
        async with httpx.AsyncClient(timeout=25,headers=self._headers()) as client:
            response=await client.get(f"{self.base_url}{path}",params=params)
            response.raise_for_status(); return response
    async def competition(self)->dict: return (await self._get("/competitions/BSA")).json()
    async def matches(self,date_from:datetime|None=None,date_to:datetime|None=None)->list[dict]:
        params={}
        if date_from: params["dateFrom"]=date_from.date().isoformat()
        if date_to: params["dateTo"]=date_to.date().isoformat()
        return (await self._get("/competitions/BSA/matches",params)).json().get("matches",[])
    async def standings(self)->dict: return (await self._get("/competitions/BSA/standings")).json()
    async def usage(self)->dict:
        response=await self._get("/competitions/BSA")
        return {"configured":True,"remaining_minute":response.headers.get("x-requests-available-minute"),"competition":response.json().get("name")}
