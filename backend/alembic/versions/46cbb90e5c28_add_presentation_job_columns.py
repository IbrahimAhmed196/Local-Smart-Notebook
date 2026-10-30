"""add presentation job columns

Revision ID: 46cbb90e5c28
Revises: 850466258613
Create Date: 2026-10-30 14:45:48.119463

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '46cbb90e5c28'
down_revision: Union[str, Sequence[str], None] = '850466258613'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Every new column is nullable or has a server_default,
    # so existing rows stay valid.
    with op.batch_alter_table('presentations') as batch_op:
        batch_op.add_column(sa.Column('outline', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('context', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('progress', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('cancel_requested', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('slide_versions', sa.JSON(), nullable=True))



def downgrade() -> None:
   with op.batch_alter_table('presentations') as batch_op:
        batch_op.drop_column('slide_versions')
        batch_op.drop_column('cancel_requested')
        batch_op.drop_column('progress')
        batch_op.drop_column('context')
        batch_op.drop_column('outline')

