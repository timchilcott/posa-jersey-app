"""Add events table

Revision ID: d4e5f6g7h8i9
Revises: c3d4e5f6g7h8
Create Date: 2026-02-23 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd4e5f6g7h8i9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6g7h8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('se_event_id', sa.String(), nullable=False),
        sa.Column('organization_id', sa.String(), nullable=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('event_type', sa.String(), nullable=False),
        sa.Column('sport', sa.String(), nullable=True),
        sa.Column('start_time', sa.DateTime(), nullable=True),
        sa.Column('end_time', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('location_name', sa.String(), nullable=True),
        sa.Column('location_address', sa.String(), nullable=True),
        sa.Column('location_url', sa.String(), nullable=True),
        sa.Column('location_description', sa.String(), nullable=True),
        sa.Column('teams', sa.JSON(), nullable=True),
        sa.Column('se_created_at', sa.DateTime(), nullable=True),
        sa.Column('se_updated_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('se_event_id', name='uq_se_event_id')
    )
    op.create_index(op.f('ix_events_id'), 'events', ['id'], unique=False)
    op.create_index(op.f('ix_events_se_event_id'), 'events', ['se_event_id'], unique=True)
    op.create_index(op.f('ix_events_event_type'), 'events', ['event_type'], unique=False)
    op.create_index(op.f('ix_events_sport'), 'events', ['sport'], unique=False)
    op.create_index(op.f('ix_events_start_time'), 'events', ['start_time'], unique=False)
    op.create_index('ix_event_type_start', 'events', ['event_type', 'start_time'], unique=False)
    op.create_index('ix_event_sport_start', 'events', ['sport', 'start_time'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_event_sport_start', table_name='events')
    op.drop_index('ix_event_type_start', table_name='events')
    op.drop_index(op.f('ix_events_start_time'), table_name='events')
    op.drop_index(op.f('ix_events_sport'), table_name='events')
    op.drop_index(op.f('ix_events_event_type'), table_name='events')
    op.drop_index(op.f('ix_events_se_event_id'), table_name='events')
    op.drop_index(op.f('ix_events_id'), table_name='events')
    op.drop_table('events')
