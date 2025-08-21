"""Add locked column to players

Revision ID: 63122e0e89db
Revises: 3bfc7bb3b155
Create Date: 2024-08-21 04:31:12.382556
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '63122e0e89db'
down_revision: Union[str, Sequence[str], None] = '3bfc7bb3b155'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('players', sa.Column('locked', sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column('players', 'locked')
