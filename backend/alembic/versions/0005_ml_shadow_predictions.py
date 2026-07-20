"""Predições do ML em modo sombra, isoladas do modelo ativo."""

from alembic import op
import sqlalchemy as sa

from app.models.base import Base
import app.models.ml_entities  # noqa: F401

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    if "ml_shadow_predictions" not in sa.inspect(op.get_bind()).get_table_names():
        Base.metadata.tables["ml_shadow_predictions"].create(bind=op.get_bind(), checkfirst=True)


def downgrade():
    if "ml_shadow_predictions" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("ml_shadow_predictions")
