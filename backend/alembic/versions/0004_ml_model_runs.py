"""Registra execuções e métricas dos modelos históricos."""

from alembic import op
import sqlalchemy as sa

from app.models.base import Base
import app.models.ml_entities  # noqa: F401

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    if "ml_model_runs" not in sa.inspect(op.get_bind()).get_table_names():
        Base.metadata.tables["ml_model_runs"].create(bind=op.get_bind(), checkfirst=True)


def downgrade():
    if "ml_model_runs" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("ml_model_runs")
