"""Persist processed Stripe events for idempotent webhook handling."""

import sqlalchemy as sa

from alembic import op

revision = "ab8614ef2c90"
down_revision = "9c20e81f40ab"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "billing_events",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column(
            "processed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade():
    op.drop_table("billing_events")
