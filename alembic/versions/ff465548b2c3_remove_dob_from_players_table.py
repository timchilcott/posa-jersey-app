"""Remove dob from players table

Revision ID: ff465548b2c3
Revises: d53a23e679e3
Create Date: 2025-06-17 22:57:58.412472

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ff465548b2c3'
down_revision: Union[str, Sequence[str], None] = 'd53a23e679e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('players', 'dob')


def downgrade() -> None:
    op.add_column('players', sa.Column('dob', sa.String(), nullable=True))