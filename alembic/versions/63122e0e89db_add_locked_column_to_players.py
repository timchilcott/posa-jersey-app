"""add locked column to players

Revision ID: 63122e0e89db
Revises: 067e47789ef7
Create Date: 2025-08-21 04:15:41.925290

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '63122e0e89db'
down_revision: Union[str, Sequence[str], None] = '067e47789ef7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "players",
        sa.Column("locked", sa.Boolean(), nullable=True, server_default=sa.false()),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("players", "locked")
