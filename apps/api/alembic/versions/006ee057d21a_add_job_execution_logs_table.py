"""add job_execution_logs table

Revision ID: 006ee057d21a
Revises: 474f9e6e6bcb
Create Date: 2026-03-12 16:23:02.703985

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '006ee057d21a'
down_revision: Union[str, Sequence[str], None] = '474f9e6e6bcb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'job_execution_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('job_id', sa.String(length=64), nullable=False),
        sa.Column('job_name', sa.String(length=128), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        sa.Column('records_affected', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('meta', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_job_execution_logs_job_id'), 'job_execution_logs', ['job_id'], unique=False)
    op.create_index(op.f('ix_job_execution_logs_status'), 'job_execution_logs', ['status'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_job_execution_logs_status'), table_name='job_execution_logs')
    op.drop_index(op.f('ix_job_execution_logs_job_id'), table_name='job_execution_logs')
    op.drop_table('job_execution_logs')
