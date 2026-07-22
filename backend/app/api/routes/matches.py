from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.database import get_session
from app.models.entities import Competition, Match, MatchStatus, Player, PlayerMatchStat, Team, TeamStat
from app.repositories.matches import MatchRepository
from app.schemas.matches import AnalysisOut, MatchListOut
from app.services.models import ModelInput, ensemble, poisson_matrix
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


def build_post_match_audit(
    prediction: dict,
    *,
    home_name: str,
    away_name: str,
    home_score: int,
    away_score: int,
    actual_stats: dict[str, float | None],
) -> dict:
    """Compara a predição pré-jogo preservada com o resultado observado."""
    actual_result = "home" if home_score > away_score else "away" if home_score < away_score else "draw"
    result_labels = {"home": home_name, "draw": "Empate", "away": away_name}
    predicted_result = max(("home", "draw", "away"), key=lambda key: prediction.get(key, 0))
    score_probability = prediction.get("score_probability")
    if score_probability is None and prediction.get("score"):
        poisson = ((prediction.get("models") or {}).get("poisson") or {})
        xg_home = poisson.get("xg_home", prediction.get("xg_home"))
        xg_away = poisson.get("xg_away", prediction.get("xg_away"))
        try:
            score_home, score_away = (int(value) for value in prediction["score"].split("-"))
            matrix = poisson_matrix(
                float(xg_home),
                float(xg_away),
                rho=float(poisson.get("dixon_coles_rho", -0.10)),
            )
            score_probability = float(matrix[score_home, score_away])
        except (TypeError, ValueError, IndexError):
            score_probability = None
    rows = [
        {
            "key": "result",
            "label": "Resultado 1X2",
            "predicted": result_labels[predicted_result],
            "probability": prediction.get(predicted_result),
            "actual": result_labels[actual_result],
            "hit": predicted_result == actual_result,
        },
        {
            "key": "score",
            "label": "Placar exato",
            "predicted": prediction.get("score") or "—",
            "probability": score_probability,
            "actual": f"{home_score}-{away_score}",
            "hit": prediction.get("score") == f"{home_score}-{away_score}",
        },
    ]

    def binary_row(key: str, label: str, probability_key: str, line: float, actual: float | None):
        probability = prediction.get(probability_key)
        if probability is None or actual is None:
            rows.append({"key": key, "label": label, "available": False})
            return
        predicted_over = float(probability) >= 0.5
        actual_over = actual > line
        rows.append(
            {
                "key": key,
                "label": label,
                "predicted": f"Mais de {str(line).replace('.', ',')}" if predicted_over else f"Menos de {str(line).replace('.', ',')}",
                "probability": float(probability) if predicted_over else 1 - float(probability),
                "actual": f"{actual:g} no total",
                "hit": predicted_over == actual_over,
                "available": True,
            }
        )

    goals = float(home_score + away_score)
    binary_row("goals", "Total de gols", "over_2_5", 2.5, goals)
    btts_probability = prediction.get("btts_yes")
    if btts_probability is not None:
        predicted_yes = float(btts_probability) >= 0.5
        actual_yes = home_score > 0 and away_score > 0
        rows.append(
            {
                "key": "btts",
                "label": "Ambas marcam",
                "predicted": "Sim" if predicted_yes else "Não",
                "probability": float(btts_probability) if predicted_yes else 1 - float(btts_probability),
                "actual": "Sim" if actual_yes else "Não",
                "hit": predicted_yes == actual_yes,
                "available": True,
            }
        )
    binary_row("corners", "Total de escanteios", "corners_over_9_5", 9.5, actual_stats.get("corners"))
    binary_row("cards", "Total de cartões amarelos", "cards_over_4_5", 4.5, actual_stats.get("cards"))
    binary_row("shots", "Total de chutes", "shots_over_24_5", 24.5, actual_stats.get("shots"))
    available = [row for row in rows if row.get("available", True)]
    return {
        "score": f"{home_score}-{away_score}",
        "hits": sum(bool(row.get("hit")) for row in available),
        "total": len(available),
        "rows": rows,
        "note": "Comparação com a predição pré-jogo preservada; não usa dados posteriores para recalcular o palpite.",
    }


async def post_match_audit(session: AsyncSession, match: Match, prediction: dict) -> dict | None:
    if match.status != MatchStatus.finished or match.home_score is None or match.away_score is None:
        return None
    stats = list(
        await session.scalars(select(TeamStat).where(TeamStat.match_id == match.id))
    )
    totals: dict[str, float | None] = {}
    for output_key, metric_key in (
        ("corners", "corner_kicks"),
        ("cards", "yellow_cards"),
        ("shots", "total_shots"),
    ):
        values = [
            # Para auditoria final, não aceite o fallback de metadata pré-jogo:
            # listas vazias de cartões não significam zero cartões na partida.
            team_metric(stat.metrics, {}, metric_key, is_home=stat.is_home)
            for stat in stats
        ]
        valid = [value for value in values if value is not None]
        totals[output_key] = sum(valid) if len(valid) == 2 else None
    audit = build_post_match_audit(
        prediction,
        home_name=match.home_team.name,
        away_name=match.away_team.name,
        home_score=match.home_score,
        away_score=match.away_score,
        actual_stats=totals,
    )
    player_rows = (
        await session.execute(
            select(PlayerMatchStat, Player)
            .join(Player, Player.id == PlayerMatchStat.player_id)
            .where(PlayerMatchStat.match_id == match.id, PlayerMatchStat.minutes > 0)
            .order_by(PlayerMatchStat.is_home.desc(), PlayerMatchStat.rating.desc().nullslast())
        )
    ).all()
    players = []
    for stat, player in player_rows:
        metrics = stat.metrics or {}
        shots = int(metrics.get("total_shots") or 0)
        target = int(metrics.get("shots_on_target") or 0)
        tackles = int(metrics.get("total_tackle") or 0)
        saves = int(metrics.get("saves") or 0)
        goals = int(metrics.get("goals") or 0)
        assists = int(metrics.get("goal_assist") or 0)
        cards = int(metrics.get("yellow_card") or 0) + int(metrics.get("red_card") or 0)
        hits = []
        if shots >= 1: hits.append("1+ chute")
        if shots >= 2: hits.append("2+ chutes")
        if target >= 1: hits.append("1+ no alvo")
        if tackles >= 2: hits.append("2+ desarmes")
        if cards: hits.append("Cartão")
        if goals: hits.append("Gol")
        if assists: hits.append("Assistência")
        if saves >= 3: hits.append("3+ defesas")
        if saves >= 4: hits.append("4+ defesas")
        if (stat.position == "GOL" or saves) and int(metrics.get("goals_conceded") or 0) == 0:
            hits.append("Sem sofrer gol")
        players.append({"name": player.name, "team": match.home_team.name if stat.is_home else match.away_team.name,
                        "minutes": stat.minutes, "rating": stat.rating, "hits": hits,
                        "actual": {"shots": shots, "shots_on_target": target, "tackles": tackles,
                                   "cards": cards, "goals": goals, "assists": assists, "saves": saves}})
    audit["players"] = players
    return audit


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
    return sorted(
        out,
        key=lambda x: (x["recommended"], x["decision_score"]),
        reverse=True,
    )


def serialize(m, **value_kwargs) -> dict:
    p = prediction_for(m)
    if not p:
        return {
            "id": m.id,
            "round_number": match_round_number(m),
            "kickoff": m.kickoff,
            "venue": m.venue,
            "status": m.status.value,
            "competition": m.competition.name,
            "home_team": m.home_team,
            "away_team": m.away_team,
            "favorite": None,
            "probabilities": None,
            "best_value": None,
            "model_pick": None,
        }
    vals = values_for(m, p, **value_kwargs)
    winner = max(("home", "draw", "away"), key=p.get)
    favorite = (
        m.home_team.name if winner == "home" else m.away_team.name if winner == "away" else "Empate"
    )
    latest_result_odds = {}
    for odd in sorted(m.odds, key=lambda row: row.captured_at, reverse=True):
        if odd.market == "match_result" and odd.selection not in latest_result_odds:
            latest_result_odds[odd.selection] = odd
    winner_odd = latest_result_odds.get(winner)
    winner_probability = float(p[winner])
    winner_has_value = any(
        value["market"] == "match_result"
        and value["selection"] == winner
        and value["is_value"]
        for value in vals
    )
    model_pick = {
        "market": "match_result",
        "selection": winner,
        "odd": float(winner_odd.price) if winner_odd else None,
        "estimated_probability": round(winner_probability, 4),
        "fair_odd": round(1 / winner_probability, 2) if winner_probability else None,
        "has_value": winner_has_value,
        "price_status": "com_value" if winner_has_value else "sem_value",
    }
    return {
        "id": m.id,
        "round_number": match_round_number(m),
        "kickoff": m.kickoff,
        "venue": m.venue,
        "status": m.status.value,
        "competition": m.competition.name,
        "home_team": m.home_team,
        "away_team": m.away_team,
        "favorite": favorite,
        "probabilities": {k: p[k] for k in ("home", "draw", "away")},
        "best_value": next((value for value in vals if value["recommended"]), None),
        "model_pick": model_pick,
    }


def match_round_number(match: Match) -> int | None:
    """Normaliza o número da rodada informado pelos diferentes provedores."""
    metadata = match.metadata_ or {}
    candidates = [
        metadata.get("matchday"),
        metadata.get("round"),
        (metadata.get("league") or {}).get("round"),
        (metadata.get("fixture") or {}).get("round"),
    ]
    for value in candidates:
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            digits = "".join(char if char.isdigit() else " " for char in value).split()
            if digits:
                return int(digits[-1])
    return None


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


def _player_metrics(raw: dict) -> dict:
    """Converte Bzzoiro (campos planos) e Cartola (campos agrupados) ao mesmo formato."""
    is_bzzoiro = raw.get("source") == "bzzoiro" or any(
        key in raw for key in ("player_id", "total_shots", "shots_on_target", "total_tackle")
    )
    if is_bzzoiro:
        value = lambda *keys: next(
            (_number(raw.get(key)) for key in keys if _number(raw.get(key)) is not None), 0.0
        )
        goals_conceded = value("goals_conceded", "goals_conceded_inside_box")
        return {
            "source": "bzzoiro",
            "shots": value("total_shots", "shots"),
            "shots_on_target": value("shots_on_target", "shots_on_goal"),
            "tackles": value("total_tackle", "tackles"),
            "interceptions": value("interception", "interceptions"),
            "fouls": value("fouls", "fouls_committed"),
            "fouls_drawn": value("was_fouled", "fouls_drawn"),
            "yellow_cards": value("yellow_card", "yellow_cards"),
            "red_cards": value("red_card", "red_cards"),
            "goals": value("goals"),
            "assists": value("goal_assist", "assists"),
            "goalkeeper_saves": value("saves", "goalkeeper_saves"),
            "penalties_saved": value("penalty_save", "penalties_saved"),
            "goals_conceded": goals_conceded,
            "clean_sheets": float(goals_conceded == 0 and value("minutes_played") >= 60),
        }

    return {
        "source": "cartola",
        "shots": _number((raw.get("shots") or {}).get("total")) or 0.0,
        "shots_on_target": _number((raw.get("shots") or {}).get("on")) or 0.0,
        "tackles": _number((raw.get("tackles") or {}).get("total")) or 0.0,
        "interceptions": _number((raw.get("tackles") or {}).get("interceptions")) or 0.0,
        "fouls": _number((raw.get("fouls") or {}).get("committed")) or 0.0,
        "fouls_drawn": _number((raw.get("fouls") or {}).get("drawn")) or 0.0,
        "yellow_cards": _number((raw.get("cards") or {}).get("yellow")) or 0.0,
        "red_cards": _number((raw.get("cards") or {}).get("red")) or 0.0,
        "goals": _number((raw.get("goals") or {}).get("total")) or 0.0,
        "assists": _number((raw.get("goals") or {}).get("assists")) or 0.0,
        "goalkeeper_saves": _number((raw.get("goalkeeper") or {}).get("saves")) or 0.0,
        "penalties_saved": _number((raw.get("goalkeeper") or {}).get("penalties_saved")) or 0.0,
        "goals_conceded": _number((raw.get("goalkeeper") or {}).get("goals_conceded")) or 0.0,
        "clean_sheets": _number((raw.get("goalkeeper") or {}).get("clean_sheet")) or 0.0,
    }


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

    # Scouts individuais não dependem de TeamStat. A Bzzoiro é a fonte
    # principal; o Cartola permanece como fallback por partida.
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
        # Não mistura provedores dentro da mesma partida. Quando há ao menos um
        # scout Bzzoiro, descarta os registros Cartola daquele jogo inteiro.
        bzzoiro_match_ids = {
            match.id
            for stat, _, match in player_rows
            if _player_metrics(stat.metrics or {})["source"] == "bzzoiro"
        }
        player_rows = [
            row
            for row in player_rows
            if row[2].id not in bzzoiro_match_ids
            or _player_metrics(row[0].metrics or {})["source"] == "bzzoiro"
        ]
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
            metrics = _player_metrics(stat.metrics or {})
            derived = derived_by_match[match.id]
            derived["total_shots"] += metrics["shots"]
            derived["shots_on_goal"] += metrics["shots_on_target"]
            derived["fouls"] += metrics["fouls"]
            derived["yellow_cards"] += metrics["yellow_cards"]
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
                    "position": (
                        "GOL"
                        if str(player.position or stat.position or "").upper()
                        in {"G", "GK", "GOL", "GOLEIRO", "GOALKEEPER"}
                        else (player.position or stat.position)
                    ),
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
                metrics = _player_metrics(row.metrics or {})
                shots = metrics["shots"]
                shots_on = metrics["shots_on_target"]
                tackles = metrics["tackles"]
                yellow = metrics["yellow_cards"]
                red = metrics["red_cards"]
                goals = metrics["goals"]
                assists = metrics["assists"]
                saves = metrics["goalkeeper_saves"]
                penalties_saved = metrics["penalties_saved"]
                goals_conceded = metrics["goals_conceded"]
                clean_sheet = metrics["clean_sheets"]
                totals["shots"] += shots
                totals["shots_on_target"] += shots_on
                totals["tackles"] += tackles
                totals["interceptions"] += metrics["interceptions"]
                totals["fouls"] += metrics["fouls"]
                totals["fouls_drawn"] += metrics["fouls_drawn"]
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
            # Proteção para partidas antigas cujo lineup não trouxe a posição.
            if totals["goalkeeper_saves"] > 0:
                entry["position"] = "GOL"
            recent_card_rows = rows[:5]
            recent_card_hits = sum(
                int(
                    _player_metrics(row.metrics or {})["yellow_cards"]
                    + _player_metrics(row.metrics or {})["red_cards"]
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

    visible_players = players[:12]
    if visible_players and not any(item.get("position") == "GOL" for item in visible_players):
        goalkeeper = next((item for item in players[12:] if item.get("position") == "GOL"), None)
        if goalkeeper:
            visible_players[-1] = goalkeeper

    dates = [kickoff.date().isoformat() for _, kickoff in player_match_rows]
    if not dates:
        dates = [match.kickoff.date().isoformat() for _, match in team_rows]
    return {
        "sample": max(len(team_rows), len(player_match_rows)),
        "sample_max": limit,
        "averages": averages,
        "players": visible_players,
        "player_source": (
            "bzzoiro" if recent_match_ids and bzzoiro_match_ids else
            "cartola" if recent_match_ids else None
        ),
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


@router.get("/standings")
async def standings(
    competition_id: int | None = None,
    session: AsyncSession = Depends(get_session),
):
    """Classificação calculada exclusivamente com partidas finalizadas importadas."""
    if competition_id is not None:
        competition = await session.get(Competition, competition_id)
    else:
        competition = await session.scalar(
            select(Competition)
            .where(Competition.active.is_(True), Competition.name.ilike("%Série A%"))
            .order_by(Competition.id.desc())
            .limit(1)
        )
    if not competition:
        raise HTTPException(404, "Competição não encontrada")

    finished = list(
        await session.scalars(
            select(Match).where(
                Match.competition_id == competition.id,
                Match.status == MatchStatus.finished,
                Match.home_score.is_not(None),
                Match.away_score.is_not(None),
            )
        )
    )
    team_ids = {team_id for match in finished for team_id in (match.home_team_id, match.away_team_id)}
    teams = {
        team.id: team
        for team in await session.scalars(select(Team).where(Team.id.in_(team_ids)))
    } if team_ids else {}
    table = {
        team_id: {"team": team, "played": 0, "wins": 0, "draws": 0, "losses": 0,
                  "goals_for": 0, "goals_against": 0, "points": 0}
        for team_id, team in teams.items()
    }
    for match in finished:
        home = table[match.home_team_id]
        away = table[match.away_team_id]
        home_goals, away_goals = int(match.home_score), int(match.away_score)
        for row, scored, conceded in ((home, home_goals, away_goals), (away, away_goals, home_goals)):
            row["played"] += 1
            row["goals_for"] += scored
            row["goals_against"] += conceded
        if home_goals > away_goals:
            home["wins"] += 1; home["points"] += 3; away["losses"] += 1
        elif away_goals > home_goals:
            away["wins"] += 1; away["points"] += 3; home["losses"] += 1
        else:
            home["draws"] += 1; away["draws"] += 1; home["points"] += 1; away["points"] += 1

    rows = list(table.values())
    for row in rows:
        row["goal_difference"] = row["goals_for"] - row["goals_against"]
    rows.sort(key=lambda row: (row["points"], row["wins"], row["goal_difference"], row["goals_for"]), reverse=True)
    for position, row in enumerate(rows, 1):
        row["position"] = position
        team = row["team"]
        row["team"] = {
            "id": team.id, "name": team.name, "short_name": team.short_name,
            "crest_url": team.crest_url, "elo": team.elo,
            "attack_strength": team.attack_strength, "defense_strength": team.defense_strength,
        }
    return {
        "competition_id": competition.id,
        "competition": competition.name,
        "season": competition.season,
        "source": "partidas finalizadas importadas",
        "updated_at": datetime.now(timezone.utc),
        "table": rows,
    }


@router.get("/rounds/next")
async def next_round(
    competition_id: int | None = None,
    session: AsyncSession = Depends(get_session),
):
    """Retorna todos os jogos da rodada atual ainda em disputa.

    A rodada escolhida é a menor que ainda possui partida agendada. Jogos já
    finalizados dessa mesma rodada permanecem na resposta para completar a grade.
    """
    if competition_id is not None:
        competition = await session.get(Competition, competition_id)
    else:
        competition = await session.scalar(
            select(Competition)
            .where(Competition.active.is_(True), Competition.name.ilike("%Série A%"))
            .order_by(Competition.id.desc())
            .limit(1)
        )
    if not competition:
        raise HTTPException(404, "Competição não encontrada")

    matches = await MatchRepository(session).list(competition_id=competition.id)
    now = datetime.now(timezone.utc)
    upcoming = sorted(
        (
            match
            for match in matches
            if match.status == MatchStatus.scheduled
            and match.kickoff >= now - timedelta(hours=6)
            and match_round_number(match) is not None
        ),
        key=lambda match: match.kickoff,
    )
    if not upcoming:
        raise HTTPException(404, "Nenhuma próxima rodada encontrada")

    # A rodada do próximo jogo cronológico evita que partidas antigas adiadas
    # façam a tela voltar para uma rodada incompleta do começo do campeonato.
    round_number = match_round_number(upcoming[0])
    round_matches = [match for match in matches if match_round_number(match) == round_number]
    return {
        "round": round_number,
        "competition_id": competition.id,
        "competition": competition.name,
        "season": competition.season,
        "matches": [serialize(match) for match in round_matches],
    }


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
        "lineups": m.metadata_.get("bzzoiro", {}),
        "historical_stats": historical_stats,
        "post_match_audit": await post_match_audit(session, m, p),
        "generated_at": datetime.now(timezone.utc),
    }
