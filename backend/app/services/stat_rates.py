"""Carrega médias de TeamStat e monta λ de escanteios/cartões/chutes.

Amostra fixa: apenas os últimos RECENT_GAMES finished do time (na competição),
sem janela longa que misture temporada antiga.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import Match, MatchStatus, TeamStat
from app.services.stat_markets import (
    DEFAULT_TEAM_RATE,
    METRIC_BY_MARKET,
    blend_rate,
    build_stat_markets,
)
from app.services.team_metrics import team_metric

# Única amostra aceita para validação / λ de mercados de stats.
RECENT_GAMES = 10


async def recent_team_stats(
    session: AsyncSession,
    team_id: int,
    *,
    venue: str = "all",
    limit: int = RECENT_GAMES,
    as_of: datetime | None = None,
    competition_id: int | None = None,
) -> list[tuple[TeamStat, Match]]:
    """Últimos N finished com TeamStat (mais recentes primeiro)."""
    reference = as_of or datetime.now(timezone.utc)
    conditions = [
        TeamStat.team_id == team_id,
        Match.status == MatchStatus.finished,
        Match.kickoff < reference,
    ]
    if competition_id is not None:
        conditions.append(Match.competition_id == competition_id)
    if venue in {"home", "away"}:
        conditions.append(TeamStat.is_home.is_(venue == "home"))
    rows = (
        await session.execute(
            select(TeamStat, Match)
            .join(Match, Match.id == TeamStat.match_id)
            .where(*conditions)
            .order_by(Match.kickoff.desc())
            .limit(limit)
        )
    ).all()
    return list(rows)


async def team_metric_average(
    session: AsyncSession,
    team_id: int,
    metric_key: str,
    *,
    venue: str = "all",
    limit: int = RECENT_GAMES,
    as_of: datetime | None = None,
    competition_id: int | None = None,
) -> tuple[float | None, int]:
    """Média nos últimos N jogos (sem cutoff antigo)."""
    rows = await recent_team_stats(
        session,
        team_id,
        venue=venue,
        limit=limit,
        as_of=as_of,
        competition_id=competition_id,
    )
    values = []
    for stat, match in rows:
        value = team_metric(stat.metrics, match.metadata_, metric_key, is_home=stat.is_home)
        if value is not None:
            values.append(value)
    if not values:
        return None, 0
    return sum(values) / len(values), len(values)


async def match_stat_lambdas(
    session: AsyncSession,
    home_team_id: int,
    away_team_id: int,
    *,
    competition_id: int | None = None,
    as_of: datetime | None = None,
) -> dict:
    """λ = média dos últimos 10 do mandante + últimos 10 do visitante (mesma competição)."""
    result = {}
    for market, metric_key in METRIC_BY_MARKET.items():
        default = DEFAULT_TEAM_RATE[market]
        home_avg, home_n = await team_metric_average(
            session,
            home_team_id,
            metric_key,
            venue="all",
            competition_id=competition_id,
            as_of=as_of,
        )
        away_avg, away_n = await team_metric_average(
            session,
            away_team_id,
            metric_key,
            venue="all",
            competition_id=competition_id,
            as_of=as_of,
        )
        home_rate = blend_rate(home_avg, home_n, default)
        away_rate = blend_rate(away_avg, away_n, default)
        sample = min(home_n, away_n) if home_n and away_n else max(home_n, away_n)
        result[market] = {
            "lambda": home_rate + away_rate,
            "home_rate": round(home_rate, 2),
            "away_rate": round(away_rate, 2),
            "sample": sample,
        }
    return result


def attach_stat_markets_to_prediction(pred: dict, rates: dict) -> dict:
    """Mescla over/under de corners/cards/shots no payload do ensemble."""
    extras = build_stat_markets(
        corners_lambda=rates["corners"]["lambda"],
        cards_lambda=rates["cards"]["lambda"],
        shots_lambda=rates["shots"]["lambda"],
        corners_sample=rates["corners"]["sample"],
        cards_sample=rates["cards"]["sample"],
        shots_sample=rates["shots"]["sample"],
    )
    merged = {**pred, **extras}
    merged["stat_rates"] = {
        market: {
            "home": rates[market]["home_rate"],
            "away": rates[market]["away_rate"],
            "total": round(rates[market]["lambda"], 2),
            "sample": rates[market]["sample"],
        }
        for market in ("corners", "cards", "shots")
    }
    return merged
