from __future__ import annotations

import httpx

from app.core.config import settings


class BzzoiroProvider:
    """Cliente mínimo da API v2; usado inicialmente como enriquecimento validável."""

    name = "bzzoiro"

    @property
    def base_url(self) -> str:
        return settings.bzzoiro_api_host.rstrip("/")

    @property
    def configured(self) -> bool:
        return bool(settings.bzzoiro_api_key)

    @property
    def headers(self) -> dict[str, str]:
        if not settings.bzzoiro_api_key:
            raise RuntimeError("BZZOIRO_API_KEY não configurada")
        return {"Authorization": f"Token {settings.bzzoiro_api_key}", "Accept": "application/json"}

    async def _get(self, path: str, params: dict | None = None):
        async with httpx.AsyncClient(timeout=40, headers=self.headers) as client:
            response = await client.get(f"{self.base_url}{path}", params=params)
            response.raise_for_status()
            return response.json()

    async def status(self) -> dict:
        if not self.configured:
            return {"configured": False, "healthy": False}
        data = await self._get("/api/v2/leagues/", {"country": "Brazil", "limit": 5})
        rows = data if isinstance(data, list) else data.get("results") or data.get("data") or []
        return {"configured": True, "healthy": True, "brazil_leagues_sample": len(rows)}

    async def events(self, date_from: str, date_to: str) -> list[dict]:
        data = await self._get(
            "/api/v2/events/",
            {"date_from": date_from, "date_to": date_to, "limit": 100, "status": "notstarted"},
        )
        return data if isinstance(data, list) else data.get("results") or data.get("data") or []

    async def lineups(self, event_id: int) -> dict:
        return await self._get(f"/api/v2/events/{event_id}/lineups/")

    async def event_stats(self, event_id: int) -> dict:
        return await self._get(f"/api/v2/events/{event_id}/stats/")

    async def player_stats(self, event_id: int):
        return await self._get(f"/api/v2/events/{event_id}/player-stats/")

    async def odds_comparison(self, event_id: int) -> dict:
        return await self._get(f"/api/v2/events/{event_id}/odds/comparison/")
