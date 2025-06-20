"""add promo_code to registration"""

from alembic import op
import sqlalchemy as sa

revision = '70cdcc468f06'
down_revision = '067e47789ef7'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('registrations', sa.Column('promo_code', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('registrations', 'promo_code')
