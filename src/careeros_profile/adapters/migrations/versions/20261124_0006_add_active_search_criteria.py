"""Add immutable active-search criteria and transactional outbox events."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261124_0006"
down_revision: str | None = "20261123_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "search_criteria_versions",
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("profile_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("signature_id", sa.String(length=64), nullable=False),
        sa.Column("snapshot_payload", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.profile_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("version_id"),
        sa.UniqueConstraint("profile_id", "idempotency_key"),
        sa.UniqueConstraint("profile_id", "version"),
    )
    op.create_index(
        "ix_search_criteria_versions_profile_id",
        "search_criteria_versions",
        ["profile_id"],
    )
    op.create_index(
        "ix_search_criteria_versions_signature_id",
        "search_criteria_versions",
        ["signature_id"],
    )
    op.create_table(
        "profile_outbox_events",
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("profile_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.profile_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint("profile_id", "idempotency_key"),
    )
    op.create_index(
        "ix_profile_outbox_events_profile_id",
        "profile_outbox_events",
        ["profile_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_profile_outbox_events_profile_id", table_name="profile_outbox_events")
    op.drop_table("profile_outbox_events")
    op.drop_index(
        "ix_search_criteria_versions_signature_id",
        table_name="search_criteria_versions",
    )
    op.drop_index(
        "ix_search_criteria_versions_profile_id",
        table_name="search_criteria_versions",
    )
    op.drop_table("search_criteria_versions")
