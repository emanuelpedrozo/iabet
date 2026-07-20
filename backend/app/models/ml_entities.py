from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class MlSeason(Base, TimestampMixin):
    __tablename__ = "ml_seasons"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(40), index=True)
    source_league_id: Mapped[int] = mapped_column(Integer)
    source_season_id: Mapped[int] = mapped_column(Integer)
    competition: Mapped[str] = mapped_column(String(120))
    country: Mapped[str] = mapped_column(String(80), default="Brazil")
    year: Mapped[int] = mapped_column(Integer, index=True)
    import_status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    quality_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (
        UniqueConstraint("source", "source_season_id", name="uq_ml_seasons_source_season"),
    )


class MlTeam(Base, TimestampMixin):
    __tablename__ = "ml_teams"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(40), index=True)
    source_team_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(120), index=True)
    normalized_name: Mapped[str] = mapped_column(String(120), index=True)
    canonical_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (
        # O provedor pode reutilizar/corrigir IDs. O nome normalizado participa da
        # identidade para nunca fundir América Mineiro com Atlético Mineiro.
        UniqueConstraint(
            "source", "source_team_id", "normalized_name", name="uq_ml_teams_source_team_name"
        ),
    )


class MlMatch(Base, TimestampMixin):
    __tablename__ = "ml_matches"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(40), index=True)
    source_event_id: Mapped[int] = mapped_column(Integer)
    season_id: Mapped[int] = mapped_column(ForeignKey("ml_seasons.id"), index=True)
    home_team_id: Mapped[int] = mapped_column(ForeignKey("ml_teams.id"), index=True)
    away_team_id: Mapped[int] = mapped_column(ForeignKey("ml_teams.id"), index=True)
    kickoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    round_number: Mapped[int | None] = mapped_column(Integer)
    home_score: Mapped[int | None] = mapped_column(Integer)
    away_score: Mapped[int | None] = mapped_column(Integer)
    home_score_ht: Mapped[int | None] = mapped_column(Integer)
    away_score_ht: Mapped[int | None] = mapped_column(Integer)
    quality_status: Mapped[str] = mapped_column(String(20), default="valid", index=True)
    quality_issues: Mapped[list] = mapped_column(JSON, default=list)
    details_imported: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    season: Mapped[MlSeason] = relationship()
    home_team: Mapped[MlTeam] = relationship(foreign_keys=[home_team_id])
    away_team: Mapped[MlTeam] = relationship(foreign_keys=[away_team_id])
    __table_args__ = (
        UniqueConstraint("source", "source_event_id", name="uq_ml_matches_source_event"),
        Index("ix_ml_matches_training", "season_id", "quality_status", "kickoff"),
    )


class MlTeamMatchStat(Base, TimestampMixin):
    __tablename__ = "ml_team_match_stats"
    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("ml_matches.id"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("ml_teams.id"), index=True)
    is_home: Mapped[bool] = mapped_column(Boolean)
    period: Mapped[str] = mapped_column(String(20), default="full_time")
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (
        UniqueConstraint("match_id", "team_id", "period", name="uq_ml_team_stats_match_team_period"),
    )


class MlPlayer(Base, TimestampMixin):
    __tablename__ = "ml_players"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(40), index=True)
    source_player_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(140), index=True)
    normalized_name: Mapped[str] = mapped_column(String(140), index=True)
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (
        UniqueConstraint("source", "source_player_id", name="uq_ml_players_source_player"),
    )


class MlPlayerMatchStat(Base, TimestampMixin):
    __tablename__ = "ml_player_match_stats"
    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("ml_matches.id"), index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("ml_players.id"), index=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("ml_teams.id"), nullable=True, index=True)
    is_home: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    started: Mapped[bool] = mapped_column(Boolean, default=False)
    minutes: Mapped[int | None] = mapped_column(Integer)
    position: Mapped[str | None] = mapped_column(String(30))
    rating: Mapped[float | None] = mapped_column(Float)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (
        UniqueConstraint("match_id", "player_id", name="uq_ml_player_stats_match_player"),
    )


class MlModelRun(Base, TimestampMixin):
    __tablename__ = "ml_model_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    algorithm: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), default="completed", index=True)
    train_seasons: Mapped[list] = mapped_column(JSON, default=list)
    test_season: Mapped[int] = mapped_column(Integer)
    train_samples: Mapped[int] = mapped_column(Integer)
    test_samples: Mapped[int] = mapped_column(Integer)
    features: Mapped[list] = mapped_column(JSON, default=list)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    artifact: Mapped[dict] = mapped_column(JSON, default=dict)


class MlShadowPrediction(Base, TimestampMixin):
    __tablename__ = "ml_shadow_predictions"
    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    model_run_id: Mapped[int] = mapped_column(ForeignKey("ml_model_runs.id"), index=True)
    probabilities: Mapped[dict] = mapped_column(JSON)
    features: Mapped[dict] = mapped_column(JSON, default=dict)
    comparison: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (
        UniqueConstraint("match_id", "model_run_id", name="uq_ml_shadow_match_model"),
    )
