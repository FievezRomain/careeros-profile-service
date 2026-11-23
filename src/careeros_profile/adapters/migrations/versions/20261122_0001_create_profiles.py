"""Create the Profile Service-owned profiles table."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261122_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "profiles",
        sa.Column("profile_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("owner_account_id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("profile_id"),
    )
    op.create_index("ix_profiles_owner_account_id", "profiles", ["owner_account_id"])
    op.create_index("ix_profiles_tenant_id", "profiles", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_profiles_tenant_id", table_name="profiles")
    op.drop_index("ix_profiles_owner_account_id", table_name="profiles")
    op.drop_table("profiles")
