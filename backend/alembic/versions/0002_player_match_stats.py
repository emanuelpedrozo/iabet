"""Estatísticas individuais por jogador e partida."""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "player_match_stats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("match_id", sa.Integer(), sa.ForeignKey("matches.id"), nullable=False),
        sa.Column("is_home", sa.Boolean(), nullable=False),
        sa.Column("started", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("minutes", sa.Integer(), nullable=True),
        sa.Column("position", sa.String(length=30), nullable=True),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("player_id", "match_id", name="uq_player_match_stats_player_match"),
    )
    op.create_index("ix_player_match_stats_player_id", "player_match_stats", ["player_id"])
    op.create_index("ix_player_match_stats_team_id", "player_match_stats", ["team_id"])
    op.create_index("ix_player_match_stats_match_id", "player_match_stats", ["match_id"])
    op.create_index("ix_player_match_stats_team_match", "player_match_stats", ["team_id", "match_id"])


def downgrade():
    op.drop_table("player_match_stats")
