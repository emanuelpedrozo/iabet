import httpx


class CartolaProvider:
    """Cliente somente-leitura para os endpoints públicos usados pelo Cartola."""

    name = "cartola"
    base_url = "https://api.cartola.globo.com"

    async def _get(self, path: str) -> dict:
        async with httpx.AsyncClient(
            timeout=30,
            headers={"User-Agent": "IABet/1.0", "Accept": "application/json"},
        ) as client:
            response = await client.get(f"{self.base_url}{path}")
            response.raise_for_status()
            return response.json()

    async def status(self) -> dict:
        data = await self._get("/mercado/status")
        return {
            "configured": True,
            "round": data.get("rodada_atual"),
            "market_status": data.get("status_mercado"),
        }

    async def round_status(self) -> dict:
        return await self._get("/mercado/status")

    async def fixtures(self, round_number: int) -> dict:
        return await self._get(f"/partidas/{round_number}")

    async def scored_players(self, round_number: int) -> dict:
        return await self._get(f"/atletas/pontuados/{round_number}")


def cartola_metrics(scout: dict | None) -> dict:
    """Converte scouts do Cartola para o formato individual interno."""
    raw = scout or {}
    goals = float(raw.get("G") or 0)
    saved = float(raw.get("FD") or 0)
    off = float(raw.get("FF") or 0)
    woodwork = float(raw.get("FT") or 0)
    return {
        "source": "cartola",
        "shots": {
            "total": goals + saved + off + woodwork,
            "on": goals + saved,
            "off": off,
            "woodwork": woodwork,
        },
        "tackles": {"total": float(raw.get("DS") or 0), "interceptions": None},
        "fouls": {
            "committed": float(raw.get("FC") or 0),
            "drawn": float(raw.get("FS") or 0),
        },
        "cards": {
            "yellow": float(raw.get("CA") or 0),
            "red": float(raw.get("CV") or 0),
        },
        "goals": {"total": goals, "assists": float(raw.get("A") or 0)},
        "goalkeeper": {
            "saves": float(raw.get("DE") or 0),
            "penalties_saved": float(raw.get("DP") or 0),
            "goals_conceded": float(raw.get("GS") or 0),
            "clean_sheet": float(raw.get("SG") or 0),
        },
        "cartola_scout": raw,
    }
