import httpx

from app.core.config import settings


class ApiSportsProvider:
    name = "api_sports"
    brasileirao_leagues = {"A": 71, "B": 72}

    @property
    def base_url(self) -> str:
        return settings.api_sports_host.rstrip("/")

    async def _get(self, path: str, params: dict | None = None) -> dict:
        if not settings.api_sports_key:
            raise RuntimeError("API_SPORTS_KEY não configurada")
        async with httpx.AsyncClient(
            timeout=45,
            headers={"x-apisports-key": settings.api_sports_key},
        ) as client:
            response = await client.get(f"{self.base_url}{path}", params=params)
            response.raise_for_status()
            data = response.json()
        errors = data.get("errors") or {}
        if errors:
            message = "; ".join(f"{key}: {value}" for key, value in errors.items())
            raise RuntimeError(f"API-Sports: {message}")
        return data

    async def status(self) -> dict:
        data = await self._get("/status")
        response = data.get("response") or {}
        subscription = response.get("subscription") or {}
        requests = response.get("requests") or {}
        return {
            "configured": True,
            "plan": subscription.get("plan"),
            "requests_current": requests.get("current"),
            "requests_limit_day": requests.get("limit_day"),
        }

    async def fixtures(self, season: int = 2024, division: str = "A") -> list[dict]:
        league_id = self.brasileirao_leagues.get(division.upper())
        if not league_id:
            raise ValueError("Divisão deve ser A ou B")
        data = await self._get(
            "/fixtures",
            {"league": league_id, "season": season},
        )
        return data.get("response") or []

    async def fixture(self, fixture_id: int) -> dict:
        data = await self._get("/fixtures", {"id": fixture_id})
        rows = data.get("response") or []
        if not rows:
            raise ValueError(f"Partida {fixture_id} não encontrada na API-Sports")
        return rows[0]
