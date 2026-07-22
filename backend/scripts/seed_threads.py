from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.email_thread import EmailThread


def seed_threads() -> None:
    now = datetime.now(UTC)

    demo_threads = [
        EmailThread(
            user_id=1,
            gmail_thread_id="demo-thread-001",
            subject="Interview scheduling",
            snippet="Please confirm your availability for next Tuesday.",
            participants="recruiter@example.com",
            message_count=3,
            latest_message_at=now,
        ),
        EmailThread(
            user_id=1,
            gmail_thread_id="demo-thread-002",
            subject="ECE project deadline",
            snippet="The final report must be submitted by Friday.",
            participants="professor@example.edu",
            message_count=5,
            latest_message_at=now - timedelta(hours=1),
        ),
        EmailThread(
            user_id=1,
            gmail_thread_id="demo-thread-003",
            subject="Order shipped",
            snippet="Your order has shipped and will arrive tomorrow.",
            participants="orders@example.com",
            message_count=2,
            latest_message_at=now - timedelta(hours=2),
        ),
    ]

    gmail_thread_ids = [thread.gmail_thread_id for thread in demo_threads]

    with SessionLocal() as database:
        existing_ids = set(
            database.scalars(
                select(EmailThread.gmail_thread_id).where(
                    EmailThread.gmail_thread_id.in_(gmail_thread_ids)
                )
            )
        )

        new_threads = [
            thread
            for thread in demo_threads
            if thread.gmail_thread_id not in existing_ids
        ]

        database.add_all(new_threads)
        database.commit()

        print(f"Inserted {len(new_threads)} demo threads.")


if __name__ == "__main__":
    seed_threads()