"""Add members directory tables

Revision ID: d4e5f6g7h8i9
Revises: c3d4e5f6g7h8
Create Date: 2026-02-24 10:00:00.000000
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
    op.create_table('members',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('se_profile_id', sa.Integer(), nullable=False),
        sa.Column('first_name', sa.String(), nullable=False),
        sa.Column('last_name', sa.String(), nullable=False),
        sa.Column('middle_name', sa.String(), nullable=True),
        sa.Column('preferred_name', sa.String(), nullable=True),
        sa.Column('suffix', sa.String(), nullable=True),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('phone', sa.String(), nullable=True),
        sa.Column('date_of_birth', sa.String(), nullable=True),
        sa.Column('gender', sa.String(), nullable=True),
        sa.Column('graduation_year', sa.Integer(), nullable=True),
        sa.Column('photo_url', sa.String(), nullable=True),
        sa.Column('address1', sa.String(), nullable=True),
        sa.Column('address2', sa.String(), nullable=True),
        sa.Column('city', sa.String(), nullable=True),
        sa.Column('state', sa.String(), nullable=True),
        sa.Column('postal_code', sa.String(), nullable=True),
        sa.Column('country', sa.String(), nullable=True),
        sa.Column('memberships', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('se_profile_id')
    )
    op.create_index(op.f('ix_members_id'), 'members', ['id'], unique=False)
    op.create_index(op.f('ix_members_se_profile_id'), 'members', ['se_profile_id'], unique=True)
    op.create_index(op.f('ix_members_email'), 'members', ['email'], unique=False)
    op.create_index('ix_member_name', 'members', ['last_name', 'first_name'], unique=False)

    op.create_table('member_guardians',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('member_id', sa.Integer(), nullable=False),
        sa.Column('first_name', sa.String(), nullable=False),
        sa.Column('last_name', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('phone', sa.String(), nullable=True),
        sa.Column('photo_url', sa.String(), nullable=True),
        sa.Column('guardian_type', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_member_guardians_id'), 'member_guardians', ['id'], unique=False)
    op.create_index('ix_guardian_member', 'member_guardians', ['member_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_guardian_member', table_name='member_guardians')
    op.drop_index(op.f('ix_member_guardians_id'), table_name='member_guardians')
    op.drop_table('member_guardians')
    op.drop_index('ix_member_name', table_name='members')
    op.drop_index(op.f('ix_members_email'), table_name='members')
    op.drop_index(op.f('ix_members_se_profile_id'), table_name='members')
    op.drop_index(op.f('ix_members_id'), table_name='members')
    op.drop_table('members')
