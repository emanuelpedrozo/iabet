from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.database import get_session
from app.models.entities import Match, MatchStatus, TeamStat
from app.repositories.matches import MatchRepository
from app.schemas.matches import AnalysisOut, MatchListOut
from app.services.models import ModelInput, ensemble
from app.services.value import (
    allowed_totals_line,
    evaluate,
    market_probability,
    median_odd,
    multiplicative_devig,
    odds_move_pct,
)

router = APIRouter(prefix="/matches", tags=["Partidas"])


def prediction_for(m) -> dict | None:
    if m.predictions:
        return sorted(m.predictions, key=lambda x: x.created_at)[-1].probabilities
    if settings.environment == "development":
        return ensemble(
            ModelInput(
                m.home_team.attack_strength,
                m.home_team.defense_strength,
                m.away_team.attack_strength,
                m.away_team.defense_strength,
                m.home_team.elo,
                m.away_team.elo,
            )
        )
    return None


def values_for(
    m,
    pred: dict,
    *,
    home_n_games: int | None = None,
    away_n_games: int | None = None,
    has_team_stats: bool = False,
    h2h_over_boost: bool = False,
) -> list:
    """De-vig, consenso entre casas, movimento de odd e ranking."""
    # Histórico por chave (para movimento)
    history: dict[tuple, list] = {}
    for o in sorted(m.odds, key=lambda x: x.captured_at):
        if o.market == "goals_2_5" and not allowed_totals_line(o.line):
            continue
        key = (o.bookmaker, o.market, o.selection, o.line)
        history.setdefault(key, []).append(o)

    latest = {k: rows[-1] for k, rows in history.items()}

    # Consenso: mediana das odds atuais por (market, selection, line)
    consensus_prices: dict[tuple, list[float]] = {}
    for o in latest.values():
        ck = (o.market, o.selection, o.line)
        consensus_prices.setdefault(ck, []).append(float(o.price))
    consensus = {k: median_odd(v) for k, v in consensus_prices.items()}
    books_count = {k: len(v) for k, v in consensus_prices.items()}

    # De-vig por bookmaker+mercado+linha
    groups: dict[tuple, dict[str, float]] = {}
    for o in latest.values():
        groups.setdefault((o.bookmaker, o.market, o.line), {})[o.selection] = float(o.price)
    fair_by_group = {
        key: multiplicative_devig(prices) for key, prices in groups.items() if len(prices) >= 2
    }

    out = []
    for key, o in latest.items():
        p = market_probability(pred, o.market, o.selection, o.line)
        if p is None:
            continue
        fair = fair_by_group.get((o.bookmaker, o.market, o.line), {}).get(o.selection)
        ck = (o.market, o.selection, o.line)
        hist = history.get(key) or [o]
        move = odds_move_pct(float(hist[0].price), float(hist[-1].price)) if len(hist) >= 2 else None
        item = evaluate(
            o.market,
            o.selection,
            o.price,
            p,
            o.bookmaker,
            fair_implied=fair,
            pred=pred,
            consensus_odd=consensus.get(ck),
            odds_move_pct_value=move,
            books_covering=books_count.get(ck, 1),
            home_n_games=home_n_games,
            away_n_games=away_n_games,
            has_team_stats=has_team_stats,
            h2h_over_boost=h2h_over_boost,
            line=o.line,
        )
        if item["is_value"]:
            out.append(item)
    return sorted(out, key=lambda x: x["rank_score"], reverse=True)


def serialize(m, **value_kwargs) -> dict:
    p = prediction_for(m)
    if not p:
        return {
            "id": m.id,
            "kickoff": m.kickoff,
            "venue": m.venue,
            "status": m.status.value,
            "competition": m.competition.name,
            "home_team": m.home_team,
            "away_team": m.away_team,
            "favorite": None,
            "probabilities": None,
            "best_value": None,
        }
    vals = values_for(m, p, **value_kwargs)
    winner = max(("home", "draw", "away"), key=p.get)
    favorite = (
        m.home_team.name if winner == "home" else m.away_team.name if winner == "away" else "Empate"
    )
    return {
        "id": m.id,
        "kickoff": m.kickoff,
        "venue": m.venue,
        "status": m.status.value,
        "competition": m.competition.name,
        "home_team": m.home_team,
        "away_team": m.away_team,
        "favorite": favorite,
        "probabilities": {k: p[k] for k in ("home", "draw", "away")},
        "best_value": vals[0] if vals else None,
    }


async def fetch_h2h(session: AsyncSession, home_id: int, away_id: int, limit: int = 10) -> list[dict]:
    rows = list(
        await session.scalars(
            select(Match)
            .where(
                Match.status == MatchStatus.finished,
                Match.home_score.is_not(None),
                Match.away_score.is_not(None),
                or_(
                    and_(Match.home_team_id == home_id, Match.away_team_id == away_id),
                    and_(Match.home_team_id == away_id, Match.away_team_id == home_id),
                ),
            )
            .order_by(Match.kickoff.desc())
            .limit(limit)
        )
    )
    out = []
    for r in rows:
        out.append(
            {
                "kickoff": r.kickoff,
                "home_team_id": r.home_team_id,
                "away_team_id": r.away_team_id,
                "home_score": r.home_score,
                "away_score": r.away_score,
                "total_goals": (r.home_score or 0) + (r.away_score or 0),
            }
        )
    return out


def h2h_over25_rate(h2h: list[dict]) -> float | None:
    if len(h2h) < 3:
        return None
    overs = sum(1 for g in h2h if g["total_goals"] > 2)
    return overs / len(h2h)


@router.get("", response_model=list[MatchListOut])
async def list_matches(
    date: datetime | None = None,
    competition_id: int | None = None,
    session: AsyncSession = Depends(get_session),
):
    start = date or datetime.now(timezone.utc) - timedelta(hours=3)
    end = (date + timedelta(days=1)) if date else start + timedelta(days=14)
    return [serialize(m) for m in await MatchRepository(session).list(start, end, competition_id)]


@router.get("/{match_id}", response_model=AnalysisOut)
async def match_analysis(match_id: int, session: AsyncSession = Depends(get_session)):
    m = await MatchRepository(session).get(match_id)
    if not m:
        raise HTTPException(404, "Partida não encontrada")
    p = prediction_for(m)
    if not p:
        raise HTTPException(503, "Predição ainda não materializada para esta partida")

    h2h = await fetch_h2h(session, m.home_team_id, m.away_team_id)
    over_rate = h2h_over25_rate(h2h)
    h2h_boost = bool(over_rate is not None and over_rate > 0.60)

    home_n = len(
        list(
            await session.scalars(
                select(Match.id).where(
                    Match.status == MatchStatus.finished,
                    Match.home_score.is_not(None),
                    or_(Match.home_team_id == m.home_team_id, Match.away_team_id == m.home_team_id),
                )
            )
        )
    )
    away_n = len(
        list(
            await session.scalars(
                select(Match.id).where(
                    Match.status == MatchStatus.finished,
                    Match.home_score.is_not(None),
                    or_(Match.home_team_id == m.away_team_id, Match.away_team_id == m.away_team_id),
                )
            )
        )
    )
    stats_n = await session.scalar(
        select(TeamStat.id)
        .where(or_(TeamStat.team_id == m.home_team_id, TeamStat.team_id == m.away_team_id))
        .limit(1)
    )
    value_kwargs = {
        "home_n_games": home_n,
        "away_n_games": away_n,
        "has_team_stats": stats_n is not None,
        "h2h_over_boost": h2h_boost,
    }

    odds = [
        {
            "bookmaker": o.bookmaker,
            "market": o.market,
            "selection": o.selection,
            "line": o.line,
            "price": o.price,
            "captured_at": o.captured_at,
        }
        for o in sorted(m.odds, key=lambda x: x.captured_at, reverse=True)
    ]
    return {
        "match": serialize(m, **value_kwargs),
        "prediction": p,
        "odds": odds,
        "value_bets": values_for(m, p, **value_kwargs),
        "comparison": {
            "elo": {"home": m.home_team.elo, "away": m.away_team.elo},
            "attack": {
                "home": m.home_team.attack_strength,
                "away": m.away_team.attack_strength,
            },
            "defense": {
                "home": m.home_team.defense_strength,
                "away": m.away_team.defense_strength,
            },
        },
        "h2h": h2h,
        "players": m.metadata_.get("players", {}),
        "generated_at": datetime.now(timezone.utc),
    }
