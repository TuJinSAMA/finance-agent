"""add stock_events table

Revision ID: a1b2c3d4e5f6
Revises: 67a63c189a64
Create Date: 2026-03-10 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '67a63c189a64'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('stock_events',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('stock_id', sa.Integer(), nullable=False),
    sa.Column('event_date', sa.Date(), nullable=False),
    sa.Column('event_type', sa.String(length=20), nullable=False),
    sa.Column('source', sa.String(length=100), nullable=True),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('content', sa.Text(), nullable=True),
    sa.Column('url', sa.String(length=500), nullable=True),
    sa.Column('sentiment', sa.String(length=10), nullable=True),
    sa.Column('impact_score', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('catalyst_type', sa.String(length=50), nullable=True),
    sa.Column('time_horizon', sa.String(length=10), nullable=True),
    sa.Column('key_point', sa.Text(), nullable=True),
    sa.Column('risk_note', sa.Text(), nullable=True),
    sa.Column('analysis', sa.Text(), nullable=True),
    sa.Column('is_analyzed', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['stock_id'], ['stocks.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('stock_id', 'title', 'event_date', name='uq_stock_event')
    )
    op.create_index('idx_events_stock_date', 'stock_events', ['stock_id', 'event_date'], unique=False, postgresql_ops={'event_date': 'DESC'})
    op.create_index('idx_events_date', 'stock_events', ['event_date'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_events_date', table_name='stock_events')
    op.drop_index('idx_events_stock_date', table_name='stock_events', postgresql_ops={'event_date': 'DESC'})
    op.drop_table('stock_events')
