"""ranking interaction fields

Revision ID: 20260801_0002
Revises: 20260801_0001
Create Date: 2026-08-01
"""

from alembic import op
import sqlalchemy as sa

revision = "20260801_0002"
down_revision = "20260801_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "score_snapshots",
        sa.Column("technical_trend", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "score_snapshots",
        sa.Column("main_positive_signal", sa.Text(), nullable=True),
    )
    op.add_column(
        "score_snapshots",
        sa.Column("main_risk", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_scores_build_trend", "score_snapshots",
        ["build_id", "technical_trend"], unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_scores_build_trend", table_name="score_snapshots")
    op.drop_column("score_snapshots", "main_risk")
    op.drop_column("score_snapshots", "main_positive_signal")
    op.drop_column("score_snapshots", "technical_trend")
