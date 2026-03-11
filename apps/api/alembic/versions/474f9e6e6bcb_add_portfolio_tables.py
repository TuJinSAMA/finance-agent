"""add portfolio tables

Revision ID: 474f9e6e6bcb
Revises: e2cb6c6dba55
Create Date: 2026-03-10 17:37:40.583071

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '474f9e6e6bcb'
down_revision: Union[str, Sequence[str], None] = 'e2cb6c6dba55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('portfolios',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=100), server_default='默认组合', nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'name')
    )
    op.create_table('portfolio_alerts',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('stock_id', sa.Integer(), nullable=False),
    sa.Column('event_id', sa.Integer(), nullable=True),
    sa.Column('alert_type', sa.String(length=30), nullable=False),
    sa.Column('alert_date', sa.Date(), nullable=False),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('content', sa.Text(), nullable=True),
    sa.Column('is_read', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['event_id'], ['stock_events.id'], ),
    sa.ForeignKeyConstraint(['stock_id'], ['stocks.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_portfolio_alerts_user_date', 'portfolio_alerts', ['user_id', 'alert_date'], unique=False)
    op.create_table('portfolio_holdings',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('portfolio_id', sa.Integer(), nullable=False),
    sa.Column('stock_id', sa.Integer(), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('avg_cost', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('added_date', sa.Date(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['portfolio_id'], ['portfolios.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['stock_id'], ['stocks.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('portfolio_id', 'stock_id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('portfolio_holdings')
    op.drop_index('idx_portfolio_alerts_user_date', table_name='portfolio_alerts')
    op.drop_table('portfolio_alerts')
    op.drop_table('portfolios')
