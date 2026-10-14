"""Add document metadata columns (Task 3)

Revision ID: 8d2f4a6b9c13
Revises: 542a9b135937
Create Date: 2026-10-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8d2f4a6b9c13'
down_revision: Union[str, Sequence[str], None] = '542a9b135937'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default lets existing rows satisfy the NOT NULL columns.
    with op.batch_alter_table('documents') as batch_op:
        batch_op.add_column(sa.Column('file_size', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('mime_type', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('sha256', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('description', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('status', sa.String(), nullable=False, server_default='UPLOADED'))
        batch_op.add_column(sa.Column('error', sa.Text(), nullable=True))
        batch_op.create_index(batch_op.f('ix_documents_sha256'), ['sha256'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('documents') as batch_op:
        batch_op.drop_index(batch_op.f('ix_documents_sha256'))
        batch_op.drop_column('error')
        batch_op.drop_column('status')
        batch_op.drop_column('description')
        batch_op.drop_column('sha256')
        batch_op.drop_column('mime_type')
        batch_op.drop_column('file_size')
