"""Base histórica isolada para treinamento e backtesting."""

from alembic import op
import sqlalchemy as sa

from app.models.base import Base
import app.models.ml_entities  # noqa: F401

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


TABLES = (
    "ml_seasons",
    "ml_teams",
    "ml_matches",
    "ml_team_match_stats",
    "ml_players",
    "ml_player_match_stats",
)


def upgrade():
    # Bancos novos passam pela 0001, que cria o metadata atual completo.
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    pending = [Base.metadata.tables[name] for name in TABLES if name not in existing]
    Base.metadata.create_all(bind=op.get_bind(), tables=pending, checkfirst=True)


def downgrade():
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    for name in reversed(TABLES):
        if name in existing:
            op.drop_table(name)
