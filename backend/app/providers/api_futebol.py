import httpx
from app.core.config import settings

class ApiFutebolProvider:
    name="api_futebol"; base_url="https://api.api-futebol.com.br/v1"; brasileirao_id=10
    @property
    def key(self): return settings.api_futebol_key or settings.api_football_key
    async def _get(self,path:str):
        if not self.key: raise RuntimeError("API_FUTEBOL_KEY não configurada")
        async with httpx.AsyncClient(timeout=30,headers={"Authorization":f"Bearer {self.key}"}) as client:
            response=await client.get(f"{self.base_url}{path}"); response.raise_for_status(); return response
    async def championships(self)->list[dict]: return (await self._get("/campeonatos")).json()
    async def championship(self)->dict: return (await self._get(f"/campeonatos/{self.brasileirao_id}")).json()
    async def matches(self)->list[dict]:
        data=(await self._get(f"/campeonatos/{self.brasileirao_id}/partidas")).json().get("partidas",{})
        result=[]
        for phase in data.values():
            for round_matches in phase.values(): result.extend(round_matches)
        return result
    async def standings(self)->list[dict]: return (await self._get(f"/campeonatos/{self.brasileirao_id}/tabela")).json()
    async def match(self,match_id:int)->dict: return (await self._get(f"/partidas/{match_id}")).json()
    async def status(self)->dict:
        info=await self.championship()
        return {"configured":True,"healthy":True,"competition":info.get("nome_popular") or info.get("nome"),"round":info.get("rodada_atual",{}).get("nome"),"status":info.get("status")}
