import httpx
from app.core.config import settings
from app.providers.base import OddsProvider

SPORT = "soccer_brazil_campeonato"
# O endpoint em lote aceita apenas mercados principais. BTTS retorna
# INVALID_MARKET/422 nele, embora seja aceito no endpoint individual do evento.
FEATURED_MARKETS = "h2h,totals"
# BTTS, escanteios e cartões são consultados por evento (cota limitada).
EVENT_STAT_MARKETS = "btts,alternate_totals_corners,alternate_totals_cards"


class OddsApiProvider(OddsProvider):
    name = "odds_api"

    async def odds(self, external_ids: list[str]) -> list[dict]:
        if not settings.odds_api_key:
            return []
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                f"https://api.the-odds-api.com/v4/sports/{SPORT}/odds",
                params={
                    "apiKey": settings.odds_api_key,
                    "regions": "eu",
                    "markets": FEATURED_MARKETS,
                    "oddsFormat": "decimal",
                },
            )
            response.raise_for_status()
            return response.json()

    async def event_odds(self, event_id: str, markets: str = EVENT_STAT_MARKETS) -> dict:
        """Odds de mercados extras (corners/cards) para um evento."""
        if not settings.odds_api_key:
            return {}
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                f"https://api.the-odds-api.com/v4/sports/{SPORT}/events/{event_id}/odds",
                params={
                    "apiKey": settings.odds_api_key,
                    "regions": "eu",
                    "markets": markets,
                    "oddsFormat": "decimal",
                },
            )
            response.raise_for_status()
            return response.json()

    async def usage(self) -> dict:
        if not settings.odds_api_key:
            return {"configured": False}
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                "https://api.the-odds-api.com/v4/sports",
                params={"apiKey": settings.odds_api_key},
            )
            response.raise_for_status()
            return {
                "configured": True,
                "remaining": response.headers.get("x-requests-remaining"),
                "used": response.headers.get("x-requests-used"),
            }
