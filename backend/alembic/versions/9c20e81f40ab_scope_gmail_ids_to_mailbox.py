"""Scope provider IDs to their owning mailbox and thread.

Revision ID: 9c20e81f40ab
Revises: 0b92e7873fad
"""

from alembic import op

revision = "9c20e81f40ab"
down_revision = "0b92e7873fad"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_email_threads_gmail_thread_id", table_name="email_threads")
    op.create_index(
        "ix_email_threads_gmail_thread_id",
        "email_threads",
        ["user_id", "gmail_thread_id"],
        unique=True,
    )
    op.drop_index("ix_email_messages_gmail_message_id", table_name="email_messages")
    op.create_index(
        "ix_email_messages_gmail_message_id",
        "email_messages",
        ["thread_id", "gmail_message_id"],
        unique=True,
    )


def downgrade() -> None:
    # Fails safely if different mailboxes contain duplicate provider IDs; never delete mail.
    op.drop_index("ix_email_messages_gmail_message_id", table_name="email_messages")
    op.create_index(
        "ix_email_messages_gmail_message_id", "email_messages", ["gmail_message_id"], unique=True
    )
    op.drop_index("ix_email_threads_gmail_thread_id", table_name="email_threads")
    op.create_index(
        "ix_email_threads_gmail_thread_id", "email_threads", ["gmail_thread_id"], unique=True
    )
