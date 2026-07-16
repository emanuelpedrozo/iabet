"""Schema inicial do domínio.

Esta revisão cria o schema completo via metadata (adequado ao bootstrap).
Mudanças futuras devem usar `alembic revision --autogenerate` com operações
incrementais (op.add_column, op.create_index, etc.), sem novo create_all.
"""
from alembic import op
from app.models.base import Base
import app.models.entities  # noqa: F401 — registra tabelas no metadata

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    Base.metadata.create_all(bind=op.get_bind())


def downgrade():
    Base.metadata.drop_all(bind=op.get_bind())
