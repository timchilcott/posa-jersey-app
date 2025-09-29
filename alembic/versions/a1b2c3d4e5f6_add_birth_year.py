"""Add birth_year column to players

Revision ID: a1b2c3d4e5f6
Revises: 63122e0e89db
Create Date: 2025-01-15 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '63122e0e89db'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('players', sa.Column('birth_year', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('players', 'birth_year')
