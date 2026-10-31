"""Add chat features and artifact metadata."""

from alembic import op
import sqlalchemy as sa

revision = "c3a7e1b92f64"
down_revision = "850466258613"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column(
            "feature",
            sa.String(),
            nullable=False,
            server_default="chat",
        ),
    )
    op.add_column(
        "messages",
        sa.Column("artifact_path", sa.String(), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("artifact_type", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("messages", "artifact_type")
    op.drop_column("messages", "artifact_path")
    op.drop_column("messages", "feature")