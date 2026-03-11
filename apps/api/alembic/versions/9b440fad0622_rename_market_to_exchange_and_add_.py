"""rename market to exchange and add market field

Revision ID: 9b440fad0622
Revises: 0ca32dcce540
Create Date: 2026-03-10 15:58:21.694173

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '9b440fad0622'
down_revision: Union[str, Sequence[str], None] = '0ca32dcce540'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add exchange column (nullable first so we can populate it)
    op.add_column('stocks', sa.Column('exchange', sa.String(length=10), nullable=True))

    # 2. Copy existing market data (SH/SZ/BJ) into exchange
    op.execute("UPDATE stocks SET exchange = market")

    # 3. Make exchange non-nullable
    op.alter_column('stocks', 'exchange', nullable=False)

    # 4. Overwrite market with 'CN_A' and add server_default
    op.execute("UPDATE stocks SET market = 'CN_A'")
    op.alter_column('stocks', 'market', server_default='CN_A')


def downgrade() -> None:
    # Restore market from exchange values, remove exchange column
    op.execute("UPDATE stocks SET market = exchange")
    op.alter_column('stocks', 'market', server_default=None)
    op.drop_column('stocks', 'exchange')
