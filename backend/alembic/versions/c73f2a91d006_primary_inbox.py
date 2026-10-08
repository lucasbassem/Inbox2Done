"""Keep only verified Primary inbox threads visible and eligible for analysis."""

import sqlalchemy as sa

from alembic import op

revision = "c73f2a91d006"
down_revision = "ab8614ef2c90"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "email_threads",
        sa.Column("is_primary_inbox", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade():
    op.drop_column("email_threads", "is_primary_inbox")
