import enum
from datetime import datetime
from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin

class MatchStatus(str, enum.Enum): scheduled="scheduled"; live="live"; finished="finished"; postponed="postponed"
class User(Base, TimestampMixin):
    __tablename__="users"; id: Mapped[int]=mapped_column(primary_key=True); email: Mapped[str]=mapped_column(String(255),unique=True,index=True); password_hash: Mapped[str]=mapped_column(String(255)); role: Mapped[str]=mapped_column(String(20),default="user"); active: Mapped[bool]=mapped_column(Boolean,default=True)
class Competition(Base, TimestampMixin):
    __tablename__="competitions"; id: Mapped[int]=mapped_column(primary_key=True); name: Mapped[str]=mapped_column(String(120)); country: Mapped[str]=mapped_column(String(80)); season: Mapped[str]=mapped_column(String(20)); sport: Mapped[str]=mapped_column(String(30),default="football"); active: Mapped[bool]=mapped_column(Boolean,default=True)
class Team(Base, TimestampMixin):
    __tablename__="teams"; id: Mapped[int]=mapped_column(primary_key=True); name: Mapped[str]=mapped_column(String(120),unique=True,index=True); short_name: Mapped[str]=mapped_column(String(30)); crest_url: Mapped[str|None]=mapped_column(String(500)); elo: Mapped[float]=mapped_column(Float,default=1500); attack_strength: Mapped[float]=mapped_column(Float,default=1); defense_strength: Mapped[float]=mapped_column(Float,default=1)
class Match(Base, TimestampMixin):
    __tablename__="matches"; id: Mapped[int]=mapped_column(primary_key=True); competition_id: Mapped[int]=mapped_column(ForeignKey("competitions.id"),index=True); home_team_id: Mapped[int]=mapped_column(ForeignKey("teams.id"),index=True); away_team_id: Mapped[int]=mapped_column(ForeignKey("teams.id"),index=True); kickoff: Mapped[datetime]=mapped_column(DateTime(timezone=True),index=True); venue: Mapped[str|None]=mapped_column(String(180)); status: Mapped[MatchStatus]=mapped_column(Enum(MatchStatus),default=MatchStatus.scheduled,index=True); home_score: Mapped[int|None]=mapped_column(Integer); away_score: Mapped[int|None]=mapped_column(Integer); metadata_: Mapped[dict]=mapped_column("metadata",JSON,default=dict)
    competition: Mapped[Competition]=relationship(); home_team: Mapped[Team]=relationship(foreign_keys=[home_team_id]); away_team: Mapped[Team]=relationship(foreign_keys=[away_team_id]); odds: Mapped[list["Odd"]]=relationship(back_populates="match",cascade="all, delete-orphan"); predictions: Mapped[list["Prediction"]]=relationship(back_populates="match",cascade="all, delete-orphan")
class TeamStat(Base, TimestampMixin):
    __tablename__="team_stats"; id: Mapped[int]=mapped_column(primary_key=True); team_id: Mapped[int]=mapped_column(ForeignKey("teams.id"),index=True); match_id: Mapped[int]=mapped_column(ForeignKey("matches.id"),index=True); is_home: Mapped[bool]=mapped_column(Boolean); metrics: Mapped[dict]=mapped_column(JSON,default=dict); __table_args__=(UniqueConstraint("team_id","match_id"),)
class Player(Base, TimestampMixin):
    __tablename__="players"; id: Mapped[int]=mapped_column(primary_key=True); team_id: Mapped[int]=mapped_column(ForeignKey("teams.id"),index=True); name: Mapped[str]=mapped_column(String(120),index=True); position: Mapped[str]=mapped_column(String(30)); status: Mapped[str]=mapped_column(String(20),default="available"); start_probability: Mapped[float]=mapped_column(Float,default=.5); stats: Mapped[dict]=mapped_column(JSON,default=dict)
class Odd(Base, TimestampMixin):
    __tablename__="odds"
    id: Mapped[int]=mapped_column(primary_key=True)
    match_id: Mapped[int]=mapped_column(ForeignKey("matches.id"),index=True)
    bookmaker: Mapped[str]=mapped_column(String(60),index=True)
    market: Mapped[str]=mapped_column(String(80),index=True)
    selection: Mapped[str]=mapped_column(String(100))
    line: Mapped[float|None]=mapped_column(Float)
    price: Mapped[float]=mapped_column(Float)
    captured_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),index=True)
    match: Mapped[Match]=relationship(back_populates="odds")
    __table_args__=(Index("ix_odds_lookup","match_id","market","selection","captured_at"),)
class Prediction(Base, TimestampMixin):
    __tablename__="predictions"
    id: Mapped[int]=mapped_column(primary_key=True)
    match_id: Mapped[int]=mapped_column(ForeignKey("matches.id"),index=True)
    model_version: Mapped[str]=mapped_column(String(50))
    probabilities: Mapped[dict]=mapped_column(JSON)
    expected_home_goals: Mapped[float]=mapped_column(Float)
    expected_away_goals: Mapped[float]=mapped_column(Float)
    score_mode: Mapped[str]=mapped_column(String(10))
    features: Mapped[dict]=mapped_column(JSON,default=dict)
    match: Mapped[Match]=relationship(back_populates="predictions")
class ApiCredential(Base, TimestampMixin):
    __tablename__="api_credentials"; id: Mapped[int]=mapped_column(primary_key=True); provider: Mapped[str]=mapped_column(String(60),unique=True); encrypted_value: Mapped[str]=mapped_column(String(1000)); active: Mapped[bool]=mapped_column(Boolean,default=True)
class JobLog(Base, TimestampMixin):
    __tablename__="job_logs"; id: Mapped[int]=mapped_column(primary_key=True); job: Mapped[str]=mapped_column(String(100),index=True); status: Mapped[str]=mapped_column(String(20)); detail: Mapped[dict]=mapped_column(JSON,default=dict)

