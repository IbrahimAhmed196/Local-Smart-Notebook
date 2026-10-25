"""create presentations table

Revision ID: 850466258613
Revises: 8d2f4a6b9c13
Create Date: 2026-10-21 17:53:41.704916

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '850466258613'
down_revision: Union[str, Sequence[str], None] = '8d2f4a6b9c13'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('presentations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('notebook_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('stage', sa.String(), nullable=True),
        sa.Column('options', sa.JSON(), nullable=False),
        sa.Column('deck', sa.JSON(), nullable=True),
        sa.Column('file_path', sa.String(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['notebook_id'], ['notebooks.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_presentations_id'), 'presentations', ['id'], unique=False)
    op.create_index(op.f('ix_presentations_notebook_id'), 'presentations', ['notebook_id'], unique=False)



def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_presentations_notebook_id'), table_name='presentations')
    op.drop_index(op.f('ix_presentations_id'), table_name='presentations')
    op.drop_table('presentations')

