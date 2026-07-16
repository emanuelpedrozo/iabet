"""Estimação de forças e ELO a partir de partidas finalizadas."""
from __future__ import annotations

from collections import defaultdict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models.entities import Competition, Match, MatchStatus, Team

DEFAULT_LEAGUE_HOME = 1.42
DEFAULT_LEAGUE_AWAY = 1.08
MIN_MATCHES_FOR_STRENGTH = 3
MIN_MATCHES_FOR_LEAGUE_AVG = 5
STRENGTH_MIN = 0.5
STRENGTH_MAX = 1.8
ELO_K = 20.0
HOME_ADVANTAGE = 70.0
FORM_WINDOW = 8
FORM_DECAY = 0.85
SEASON_WEIGHT = 0.4
FORM_WEIGHT = 0.6


def clamp(value: float, lo: float = STRENGTH_MIN, hi: float = STRENGTH_MAX) -> float:
    return max(lo, min(hi, value))


def league_averages_from_scores(
    scores: list[tuple[int, int]],
    min_matches: int = MIN_MATCHES_FOR_LEAGUE_AVG,
) -> tuple[float, float]:
    """Retorna (média gols casa, média gols fora) ou defaults se amostra pequena."""
    if len(scores) < min_matches:
        return DEFAULT_LEAGUE_HOME, DEFAULT_LEAGUE_AWAY
    home = sum(h for h, _ in scores) / len(scores)
    away = sum(a for _, a in scores) / len(scores)
    return max(0.2, home), max(0.2, away)


def attack_defense_from_results(
    results: list[tuple[bool, int, int]],
    league_home: float,
    league_away: float,
    min_matches: int = MIN_MATCHES_FOR_STRENGTH,
) -> tuple[float, float] | None:
    """results: (is_home, goals_for, goals_against) em ordem cronológica."""
    if len(results) < min_matches:
        return None
    attack_ratios: list[float] = []
    defense_ratios: list[float] = []
    for is_home, gf, ga in results:
        avg_for = league_home if is_home else league_away
        avg_against = league_away if is_home else league_home
        attack_ratios.append(gf / avg_for if avg_for else 1.0)
        defense_ratios.append(ga / avg_against if avg_against else 1.0)
    return clamp(sum(attack_ratios) / len(attack_ratios)), clamp(
        sum(defense_ratios) / len(defense_ratios)
    )


def form_attack_defense(
    results: list[tuple[bool, int, int]],
    league_home: float,
    league_away: float,
    window: int = FORM_WINDOW,
    decay: float = FORM_DECAY,
    min_matches: int = MIN_MATCHES_FOR_STRENGTH,
) -> tuple[float, float] | None:
    """Forças com decay nos últimos jogos (mais peso no recente)."""
    recent = results[-window:]
    if len(recent) < min_matches:
        return None
    attack_w = defense_w = weight_sum = 0.0
    for i, (is_home, gf, ga) in enumerate(recent):
        w = decay ** (len(recent) - 1 - i)
        avg_for = league_home if is_home else league_away
        avg_against = league_away if is_home else league_home
        attack_w += w * (gf / avg_for if avg_for else 1.0)
        defense_w += w * (ga / avg_against if avg_against else 1.0)
        weight_sum += w
    if weight_sum <= 0:
        return None
    return clamp(attack_w / weight_sum), clamp(defense_w / weight_sum)


def blend_strengths(
    season: tuple[float, float] | None,
    form: tuple[float, float] | None,
) -> tuple[float, float] | None:
    if season is None and form is None:
        return None
    if form is None:
        return season
    if season is None:
        return form
    return (
        clamp(SEASON_WEIGHT * season[0] + FORM_WEIGHT * form[0]),
        clamp(SEASON_WEIGHT * season[1] + FORM_WEIGHT * form[1]),
    )


def team_profile(
    results: list[tuple[bool, int, int]],
    league_home: float,
    league_away: float,
) -> dict:
    season = attack_defense_from_results(results, league_home, league_away)
    form = form_attack_defense(results, league_home, league_away)
    overall = blend_strengths(season, form) or (1.0, 1.0)
    home_rows = [r for r in results if r[0]]
    away_rows = [r for r in results if not r[0]]
    home_s = (
        blend_strengths(
            attack_defense_from_results(home_rows, league_home, league_away),
            form_attack_defense(home_rows, league_home, league_away),
        )
        or overall
    )
    away_s = (
        blend_strengths(
            attack_defense_from_results(away_rows, league_home, league_away),
            form_attack_defense(away_rows, league_home, league_away),
        )
        or overall
    )
    return {
        "attack": overall[0],
        "defense": overall[1],
        "attack_home": home_s[0],
        "defense_home": home_s[1],
        "attack_away": away_s[0],
        "defense_away": away_s[1],
        "n_games": len(results),
        "form_games": min(FORM_WINDOW, len(results)),
    }


def apply_elo_result(
    home_elo: float,
    away_elo: float,
    home_score: int,
    away_score: int,
    k: float = ELO_K,
    home_advantage: float = HOME_ADVANTAGE,
) -> tuple[float, float]:
    expected_home = 1 / (1 + 10 ** (-((home_elo + home_advantage) - away_elo) / 400))
    if home_score > away_score:
        score_home = 1.0
    elif home_score == away_score:
        score_home = 0.5
    else:
        score_home = 0.0
    new_home = home_elo + k * (score_home - expected_home)
    new_away = away_elo + k * ((1.0 - score_home) - (1.0 - expected_home))
    return new_home, new_away


class StrengthService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self._profiles: dict[int, dict] = {}
        self._league_avgs: dict[int, tuple[float, float]] = {}

    async def league_averages_for(self, competition_id: int) -> tuple[float, float]:
        if competition_id in self._league_avgs:
            return self._league_avgs[competition_id]
        matches = list(
            await self.session.scalars(
                select(Match).where(
                    Match.competition_id == competition_id,
                    Match.status == MatchStatus.finished,
                    Match.home_score.is_not(None),
                    Match.away_score.is_not(None),
                )
            )
        )
        scores = [(m.home_score, m.away_score) for m in matches]  # type: ignore[misc]
        avgs = league_averages_from_scores(scores)
        self._league_avgs[competition_id] = avgs
        return avgs

    async def _load_profiles(self, competition_id: int) -> dict[int, dict]:
        finished = list(
            await self.session.scalars(
                select(Match)
                .where(
                    Match.competition_id == competition_id,
                    Match.status == MatchStatus.finished,
                    Match.home_score.is_not(None),
                    Match.away_score.is_not(None),
                )
                .order_by(Match.kickoff.asc())
            )
        )
        league_home, league_away = await self.league_averages_for(competition_id)
        by_team: dict[int, list[tuple[bool, int, int]]] = defaultdict(list)
        for m in finished:
            assert m.home_score is not None and m.away_score is not None
            by_team[m.home_team_id].append((True, m.home_score, m.away_score))
            by_team[m.away_team_id].append((False, m.away_score, m.home_score))
        profiles = {
            tid: team_profile(rows, league_home, league_away) for tid, rows in by_team.items()
        }
        self._profiles.update(profiles)
        return profiles

    async def match_strengths(
        self, competition_id: int, home_team_id: int, away_team_id: int
    ) -> dict:
        """Forças condicionadas ao mando para montar ModelInput."""
        profiles = await self._load_profiles(competition_id)
        default = {
            "attack": 1.0,
            "defense": 1.0,
            "attack_home": 1.0,
            "defense_home": 1.0,
            "attack_away": 1.0,
            "defense_away": 1.0,
            "n_games": 0,
            "form_games": 0,
        }
        home = profiles.get(home_team_id, default)
        away = profiles.get(away_team_id, default)
        return {
            "home_attack": home["attack_home"],
            "home_defense": home["defense_home"],
            "away_attack": away["attack_away"],
            "away_defense": away["defense_away"],
            "home_n_games": home["n_games"],
            "away_n_games": away["n_games"],
            "home_form_games": home["form_games"],
            "away_form_games": away["form_games"],
        }

    async def recalculate(self) -> dict:
        """Atualiza forças (temporada+forma) e ELO; idempotente no ELO."""
        self._profiles.clear()
        self._league_avgs.clear()
        competitions = list(await self.session.scalars(select(Competition)))
        teams_updated = 0
        elo_applied = 0
        league_stats: dict[int, tuple[float, float]] = {}

        for comp in competitions:
            finished = list(
                await self.session.scalars(
                    select(Match)
                    .where(
                        Match.competition_id == comp.id,
                        Match.status == MatchStatus.finished,
                        Match.home_score.is_not(None),
                        Match.away_score.is_not(None),
                    )
                    .options(selectinload(Match.home_team), selectinload(Match.away_team))
                    .order_by(Match.kickoff.asc())
                )
            )
            scores = [(m.home_score, m.away_score) for m in finished]  # type: ignore[misc]
            league_home, league_away = league_averages_from_scores(scores)
            league_stats[comp.id] = (league_home, league_away)
            self._league_avgs[comp.id] = (league_home, league_away)

            by_team: dict[int, list[tuple[bool, int, int]]] = defaultdict(list)
            for m in finished:
                assert m.home_score is not None and m.away_score is not None
                by_team[m.home_team_id].append((True, m.home_score, m.away_score))
                by_team[m.away_team_id].append((False, m.away_score, m.home_score))

            for team_id, results in by_team.items():
                profile = team_profile(results, league_home, league_away)
                self._profiles[team_id] = profile
                team = await self.session.get(Team, team_id)
                if not team:
                    continue
                team.attack_strength = profile["attack"]
                team.defense_strength = profile["defense"]
                teams_updated += 1

            for m in finished:
                meta = dict(m.metadata_ or {})
                if meta.get("elo_applied"):
                    continue
                assert m.home_score is not None and m.away_score is not None
                home, away = m.home_team, m.away_team
                new_home, new_away = apply_elo_result(
                    home.elo, away.elo, m.home_score, m.away_score
                )
                home.elo = round(new_home, 2)
                away.elo = round(new_away, 2)
                meta["elo_applied"] = True
                m.metadata_ = meta
                elo_applied += 1

        await self.session.commit()
        return {
            "competitions": len(competitions),
            "teams_updated": teams_updated,
            "elo_applied": elo_applied,
            "league_averages": {
                str(k): {"home": v[0], "away": v[1]} for k, v in league_stats.items()
            },
        }
