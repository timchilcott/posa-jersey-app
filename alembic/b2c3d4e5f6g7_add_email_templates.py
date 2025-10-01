"""Add email templates table

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2025-01-15 14:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6g7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('email_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('subject', sa.String(), nullable=False),
        sa.Column('body_html', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    
    # Insert default templates
    op.execute("""
        INSERT INTO email_templates (name, subject, body_html) VALUES 
        ('standard_confirmation', 
         'Jersey Numbers and Uniform Info for Your Player(s)',
         '<p>Thanks for signing up for soccer with the Pend Oreille Pines. We''re excited to have your family with us this season!</p><p>Here''s the jersey info for your player(s):</p>{player_list}<p>Promo Code: {promo_code}</p><p>Order your jerseys here:<br><a href="{uniform_url}">{uniform_url}</a></p><p>Only the reversible Pines jersey is required for games. You''re welcome to add Pines-branded black shorts and socks to your order, or use your own. Any plain black shorts and socks are just fine as long as they don''t have other team logos or colors.</p><p>If your family is in a position to purchase the jerseys without using the promo codes, it helps us stretch our nonprofit funds to support other families and improve the program. But either way, jerseys are covered and we''re thrilled to have your kids on the field.</p><p>—<br>Tim Chilcott<br>President - POSA<br>🌲 Pines stand tall.<br>❤️ The heart of sports starts with us.</p>'),
        ('pines_confirmation',
         'Jersey Numbers and Uniform Info for Your Player(s)',
         '<p>Thanks for registering with the Pend Oreille Pines High School Club Team. We''re looking forward to a strong season ahead.</p><p>Here''s the jersey info for your player(s):</p>{player_list}<p>Order your full kit here:<br><a href="{uniform_url}">{uniform_url}</a></p><p><strong>Uniform Requirements:</strong><br>All High School Club Team players are required to wear the full Pines kit:<br>• Reversible Pines jersey<br>• Pines black shorts<br>• Pines black socks</p><p>Please complete your order as soon as possible to ensure everything arrives before the first match. Promo codes are not used for this team, as club players are responsible for purchasing their full kits.</p><p>—<br>Tim Chilcott<br>President - POSA<br>🌲 Pines stand tall.<br>❤️ The heart of sports starts with us.</p>')
    """)


def downgrade() -> None:
    op.drop_table('email_templates')
