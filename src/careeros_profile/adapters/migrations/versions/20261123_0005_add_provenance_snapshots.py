"""Add fact provenance, confirmation status and immutable snapshots."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261123_0005"
down_revision: str | None = "20261123_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FACT_TABLES = ("experiences", "educations", "skills")


def upgrade() -> None:
    for table_name in FACT_TABLES:
        op.add_column(
            table_name,
            sa.Column(
                "provenance_origin",
                sa.String(length=32),
                nullable=False,
                server_default="directEntry",
            ),
        )
        op.add_column(
            table_name,
            sa.Column("provenance_source_id", sa.String(length=200), nullable=True),
        )
        op.add_column(
            table_name,
            sa.Column(
                "provenance_recorded_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
        )
        op.add_column(
            table_name,
            sa.Column(
                "validation_status",
                sa.String(length=32),
                nullable=False,
                server_default="userConfirmed",
            ),
        )

    op.create_table(
        "profile_snapshots",
        sa.Column("snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("profile_id", sa.String(length=36), nullable=False),
        sa.Column("items_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.profile_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("snapshot_id"),
    )
    op.create_index("ix_profile_snapshots_profile_id", "profile_snapshots", ["profile_id"])
    op.create_table(
        "snapshot_idempotency",
        sa.Column("profile_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.profile_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["profile_snapshots.snapshot_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("profile_id", "idempotency_key"),
    )


def downgrade() -> None:
    op.drop_table("snapshot_idempotency")
    op.drop_index("ix_profile_snapshots_profile_id", table_name="profile_snapshots")
    op.drop_table("profile_snapshots")
    for table_name in reversed(FACT_TABLES):
        op.drop_column(table_name, "validation_status")
        op.drop_column(table_name, "provenance_recorded_at")
        op.drop_column(table_name, "provenance_source_id")
        op.drop_column(table_name, "provenance_origin")
