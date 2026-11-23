"""Create owner-scoped professional experiences."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261123_0002"
down_revision: str | None = "20261122_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_profiles_tenant_owner",
        "profiles",
        ["tenant_id", "owner_account_id"],
        unique=True,
    )
    op.create_table(
        "experiences",
        sa.Column("item_id", sa.String(length=36), nullable=False),
        sa.Column("profile_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("employer", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=4000), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("current", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.profile_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("item_id"),
    )
    op.create_index("ix_experiences_profile_id", "experiences", ["profile_id"])


def downgrade() -> None:
    op.drop_index("ix_experiences_profile_id", table_name="experiences")
    op.drop_table("experiences")
    op.drop_index("uq_profiles_tenant_owner", table_name="profiles")
