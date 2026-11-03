"""merge heads

Revision ID: aa258e4a9907
Revises: 46cbb90e5c28, c3a7e1b92f64
Create Date: 2026-11-03 23:39:33.741069

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'aa258e4a9907'
down_revision: Union[str, Sequence[str], None] = ('46cbb90e5c28', 'c3a7e1b92f64')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
