"""add market_metric_values table

Revision ID: bc634f719b2e
Revises: 006ee057d21a
Create Date: 2026-04-22 12:16:40.682857

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'bc634f719b2e'
down_revision: Union[str, Sequence[str], None] = '006ee057d21a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('market_metric_values',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('as_of', sa.DateTime(timezone=True), nullable=False),
    sa.Column('group', sa.String(length=10), nullable=False),
    sa.Column('name', sa.String(length=30), nullable=False),
    sa.Column('symbol', sa.String(length=20), nullable=False),
    sa.Column('value', sa.Numeric(precision=18, scale=4), nullable=True),
    sa.Column('change_pct', sa.Numeric(precision=8, scale=4), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name', 'as_of')
    )
    op.create_index('idx_mmv_name_as_of', 'market_metric_values', ['name', 'as_of'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_mmv_name_as_of', table_name='market_metric_values')
    op.drop_table('market_metric_values')
