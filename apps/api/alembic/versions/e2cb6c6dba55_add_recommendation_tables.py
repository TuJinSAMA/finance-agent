"""add recommendation tables

Revision ID: e2cb6c6dba55
Revises: a1b2c3d4e5f6
Create Date: 2026-03-10 17:19:42.824088

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e2cb6c6dba55'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('recommendations',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('rec_date', sa.Date(), nullable=False),
    sa.Column('stock_id', sa.Integer(), nullable=False),
    sa.Column('quant_score', sa.Numeric(precision=8, scale=4), nullable=True),
    sa.Column('catalyst_score', sa.Numeric(precision=8, scale=4), nullable=True),
    sa.Column('final_score', sa.Numeric(precision=8, scale=4), nullable=True),
    sa.Column('rank', sa.Integer(), nullable=True),
    sa.Column('reason_short', sa.Text(), nullable=True),
    sa.Column('reason_detail', sa.Text(), nullable=True),
    sa.Column('price_at_rec', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('price_t1', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('price_t5', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('return_t1', sa.Numeric(precision=8, scale=4), nullable=True),
    sa.Column('return_t5', sa.Numeric(precision=8, scale=4), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['stock_id'], ['stocks.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('rec_date', 'stock_id')
    )
    op.create_index('idx_recommendations_date', 'recommendations', ['rec_date'], unique=False)
    op.create_table('user_recommendations',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('recommendation_id', sa.Integer(), nullable=False),
    sa.Column('rec_date', sa.Date(), nullable=False),
    sa.Column('is_read', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('is_favorited', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('user_feedback', sa.String(length=20), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['recommendation_id'], ['recommendations.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'recommendation_id')
    )
    op.create_index('idx_user_rec_user_date', 'user_recommendations', ['user_id', 'rec_date'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_user_rec_user_date', table_name='user_recommendations')
    op.drop_table('user_recommendations')
    op.drop_index('idx_recommendations_date', table_name='recommendations')
    op.drop_table('recommendations')
