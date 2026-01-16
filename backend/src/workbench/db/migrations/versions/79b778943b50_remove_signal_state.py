"""remove_signal_state

Revision ID: 79b778943b50
Revises: 001_initial
Create Date: 2026-01-16 09:46:13.762555

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '79b778943b50'
down_revision: Union[str, None] = '001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the state index first
    op.drop_index('ix_signals_state', table_name='signals')
    # Drop the state column
    op.drop_column('signals', 'state')


def downgrade() -> None:
    # Re-add the state column
    op.add_column('signals', sa.Column('state', sa.String(20), nullable=False, server_default='pending'))
    # Re-create the index
    op.create_index('ix_signals_state', 'signals', ['state'])
