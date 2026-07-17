from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.database import get_session
from app.models.entities import Match, MatchStatus, Player, PlayerMatchStat, TeamStat
from app.repositories.matches import MatchRepository
from app.schemas.matches import AnalysisOut, MatchListOut
from app.services.models import ModelInput, ensemble
from app.services.value import (
    allowed_stat_line,
    allowed_totals_line,
    evaluate,
    market_probability,
    median_odd,
    multiplicative_devig,
    odds_move_pct,
    STAT_MARKETS,
)
from app.services.stat_rates import (
    RECENT_GAMES,
    attach_stat_markets_to_prediction,
    match_stat_lambdas,
    recent_team_stats,
)
from app.services.team_metrics import number as _number
from app.services.team_metrics import team_metric

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


async def prediction_with_stats(session: AsyncSession, m) -> dict | None:
    """Predição materializada; completa com mercados de stats dos últimos 10 jogos."""
    pred = prediction_for(m)
    if not pred:
        return None
    if pred.get("stat_rates"):
        return pred
    rates = await match_stat_lambdas(
        session,
        m.home_team_id,
        m.away_team_id,
        competition_id=m.competition_id,
        as_of=m.kickoff,
    )
    return attach_stat_markets_to_prediction(pred, rates)


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
        if o.market in STAT_MARKETS and not allowed_stat_line(o.market, o.line):
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


def _team_metric(stat: TeamStat, match: Match, key: str, team_id: int):
    """Unifica os formatos da API-Sports e da API Futebol."""
    is_home = match.home_team_id == team_id
    return team_metric(stat.metrics, match.metadata_, key, is_home=is_home)


async def historical_detail(
    session: AsyncSession,
    team_id: int,
    limit: int = RECENT_GAMES,
    as_of: datetime | None = None,
    venue: str = "all",
    competition_id: int | None = None,
) -> dict:
    """Médias e elenco só com os últimos N jogos (sem temporada antiga)."""
    reference_date = as_of or datetime.now(timezone.utc)
    team_rows = await recent_team_stats(
        session,
        team_id,
        venue=venue,
        limit=limit,
        as_of=reference_date,
        competition_id=competition_id,
    )
    keys = ["total_shots", "shots_on_goal", "corner_kicks", "fouls", "yellow_cards", "expected_goals"]
    averages = {}
    for key in keys:
        values = [_team_metric(stat, match, key, team_id) for stat, match in team_rows]
        clean = [value for value in values if value is not None]
        averages[key] = round(sum(clean) / len(clean), 2) if clean else None

    # Scouts individuais não dependem de TeamStat. O Cartola pode fornecer
    # PlayerMatchStat mesmo quando não há estatística coletiva para a partida.
    player_conditions = [
        PlayerMatchStat.team_id == team_id,
        Match.status == MatchStatus.finished,
        Match.kickoff < reference_date,
    ]
    if competition_id is not None:
        player_conditions.append(Match.competition_id == competition_id)
    if venue == "home":
        player_conditions.append(Match.home_team_id == team_id)
    elif venue == "away":
        player_conditions.append(Match.away_team_id == team_id)
    player_match_rows = (
        await session.execute(
            select(Match.id, Match.kickoff)
            .join(PlayerMatchStat, PlayerMatchStat.match_id == Match.id)
            .where(*player_conditions)
            .distinct()
            .order_by(Match.kickoff.desc())
            .limit(limit)
        )
    ).all()
    recent_match_ids = [match_id for match_id, _ in player_match_rows]
    players: list[dict] = []
    if recent_match_ids:
        player_rows = (
            await session.execute(
                select(PlayerMatchStat, Player, Match)
                .join(Player, Player.id == PlayerMatchStat.player_id)
                .join(Match, Match.id == PlayerMatchStat.match_id)
                .where(
                    PlayerMatchStat.team_id == team_id,
                    PlayerMatchStat.match_id.in_(recent_match_ids),
                )
                .order_by(Match.kickoff.desc())
            )
        ).all()
        # Quando não há TeamStat, deriva apenas métricas coletivas que podem ser
        # somadas com segurança a partir dos scouts individuais do Cartola.
        derived_by_match = {
            match_id: {
                "total_shots": 0.0,
                "shots_on_goal": 0.0,
                "fouls": 0.0,
                "yellow_cards": 0.0,
            }
            for match_id in recent_match_ids
        }
        for stat, _, match in player_rows:
            metrics = stat.metrics or {}
            derived = derived_by_match[match.id]
            derived["total_shots"] += (
                _number((metrics.get("shots") or {}).get("total")) or 0
            )
            derived["shots_on_goal"] += (
                _number((metrics.get("shots") or {}).get("on")) or 0
            )
            derived["fouls"] += (
                _number((metrics.get("fouls") or {}).get("committed")) or 0
            )
            derived["yellow_cards"] += (
                _number((metrics.get("cards") or {}).get("yellow")) or 0
            )
        for key in derived_by_match[recent_match_ids[0]]:
            if averages[key] is None:
                averages[key] = round(
                    sum(match_values[key] for match_values in derived_by_match.values())
                    / len(derived_by_match),
                    2,
                )
        grouped: dict[int, dict] = {}
        for stat, player, _ in player_rows:
            entry = grouped.setdefault(
                player.id,
                {
                    "name": player.name,
                    "position": player.position,
                    "photo": (player.stats or {}).get("photo"),
                    "rows": [],
                },
            )
            if len(entry["rows"]) < limit:
                entry["rows"].append(stat)
        for entry in grouped.values():
            rows = entry.pop("rows")
            minutes = sum(row.minutes or 0 for row in rows)
            totals = {
                "shots": 0.0,
                "shots_on_target": 0.0,
                "tackles": 0.0,
                "interceptions": 0.0,
                "fouls": 0.0,
                "fouls_drawn": 0.0,
                "yellow_cards": 0.0,
                "red_cards": 0.0,
                "goals": 0.0,
                "assists": 0.0,
                "goalkeeper_saves": 0.0,
                "penalties_saved": 0.0,
                "goals_conceded": 0.0,
                "clean_sheets": 0.0,
            }
            hits = {
                "shot_1_plus": 0,
                "shot_2_plus": 0,
                "shot_on_target_1_plus": 0,
                "tackle_2_plus": 0,
                "card_any": 0,
                "yellow_card_any": 0,
                "red_card_any": 0,
                "goal_any": 0,
                "assist_any": 0,
                "save_3_plus": 0,
                "save_4_plus": 0,
                "clean_sheet": 0,
            }
            for row in rows:
                metrics = row.metrics or {}
                shots = _number((metrics.get("shots") or {}).get("total")) or 0
                shots_on = _number((metrics.get("shots") or {}).get("on")) or 0
                tackles = _number((metrics.get("tackles") or {}).get("total")) or 0
                yellow = _number((metrics.get("cards") or {}).get("yellow")) or 0
                red = _number((metrics.get("cards") or {}).get("red")) or 0
                goals = _number((metrics.get("goals") or {}).get("total")) or 0
                assists = _number((metrics.get("goals") or {}).get("assists")) or 0
                saves = _number((metrics.get("goalkeeper") or {}).get("saves")) or 0
                penalties_saved = _number((metrics.get("goalkeeper") or {}).get("penalties_saved")) or 0
                goals_conceded = _number((metrics.get("goalkeeper") or {}).get("goals_conceded")) or 0
                clean_sheet = _number((metrics.get("goalkeeper") or {}).get("clean_sheet")) or 0
                totals["shots"] += shots
                totals["shots_on_target"] += shots_on
                totals["tackles"] += tackles
                totals["interceptions"] += (
                    _number((metrics.get("tackles") or {}).get("interceptions")) or 0
                )
                totals["fouls"] += _number((metrics.get("fouls") or {}).get("committed")) or 0
                totals["fouls_drawn"] += _number((metrics.get("fouls") or {}).get("drawn")) or 0
                totals["yellow_cards"] += yellow
                totals["red_cards"] += red
                totals["goals"] += goals
                totals["assists"] += assists
                totals["goalkeeper_saves"] += saves
                totals["penalties_saved"] += penalties_saved
                totals["goals_conceded"] += goals_conceded
                totals["clean_sheets"] += clean_sheet
                hits["shot_1_plus"] += int(shots >= 1)
                hits["shot_2_plus"] += int(shots >= 2)
                hits["shot_on_target_1_plus"] += int(shots_on >= 1)
                hits["tackle_2_plus"] += int(tackles >= 2)
                hits["card_any"] += int(yellow + red >= 1)
                hits["yellow_card_any"] += int(yellow >= 1)
                hits["red_card_any"] += int(red >= 1)
                hits["goal_any"] += int(goals >= 1)
                hits["assist_any"] += int(assists >= 1)
                hits["save_3_plus"] += int(saves >= 3)
                hits["save_4_plus"] += int(saves >= 4)
                hits["clean_sheet"] += int(clean_sheet >= 1)
            appearances = len(rows)
            if appearances <= 1:
                continue
            recent_card_rows = rows[:5]
            recent_card_hits = sum(
                int(
                    (_number(((row.metrics or {}).get("cards") or {}).get("yellow")) or 0)
                    + (_number(((row.metrics or {}).get("cards") or {}).get("red")) or 0)
                    >= 1
                )
                for row in recent_card_rows
            )
            players.append(
                {
                    **entry,
                    "appearances": appearances,
                    "minutes": minutes or None,
                    **{
                        f"{key}_per_game": round(value / appearances, 2)
                        for key, value in totals.items()
                    },
                    **{
                        f"{key}_per90": round(value * 90 / minutes, 2) if minutes else None
                        for key, value in totals.items()
                    },
                    "hit_rates": {
                        **{key: round(value / appearances, 3) for key, value in hits.items()},
                        "card_any_last_5": round(
                            recent_card_hits / len(recent_card_rows), 3
                        ),
                    },
                    "carded_games": hits["card_any"],
                    "yellow_card_games": hits["yellow_card_any"],
                    "red_card_games": hits["red_card_any"],
                }
            )
        players.sort(
            key=lambda item: (
                item["appearances"],
                item["shots_per_game"]
                + item["tackles_per_game"]
                + item["goalkeeper_saves_per_game"],
            ),
            reverse=True,
        )

    dates = [kickoff.date().isoformat() for _, kickoff in player_match_rows]
    if not dates:
        dates = [match.kickoff.date().isoformat() for _, match in team_rows]
    return {
        "sample": max(len(team_rows), len(player_match_rows)),
        "sample_max": limit,
        "averages": averages,
        "players": players[:12],
        "players_scope": f"last_{limit}_games",
        "lineup_sample": len(recent_match_ids),
        "venue": venue,
        "period_start": min(dates) if dates else None,
        "period_end": max(dates) if dates else None,
    }


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
    p = await prediction_with_stats(session, m)
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
    historical_stats = {"limit": RECENT_GAMES, "home": {}, "away": {}}
    for venue in ("all", "home", "away"):
        historical_stats["home"][venue] = await historical_detail(
            session,
            m.home_team_id,
            as_of=m.kickoff,
            venue=venue,
            competition_id=m.competition_id,
        )
        historical_stats["away"][venue] = await historical_detail(
            session,
            m.away_team_id,
            as_of=m.kickoff,
            venue=venue,
            competition_id=m.competition_id,
        )
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
        "historical_stats": historical_stats,
        "generated_at": datetime.now(timezone.utc),
    }
