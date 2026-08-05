from datetime import UTC, datetime

from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.action_item import ActionItem
from app.models.email_thread import EmailThread
from app.models.suggested_reply import SuggestedReply
from app.models.thread_analysis import ThreadAnalysis

test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestSessionLocal = sessionmaker(
    bind=test_engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)

Base.metadata.create_all(bind=test_engine)


def clear_data() -> None:
    with TestSessionLocal() as database:
        database.query(ActionItem).delete()
        database.query(SuggestedReply).delete()
        database.query(ThreadAnalysis).delete()
        database.query(EmailThread).delete()
        database.commit()


def test_analysis_stores_actions_and_replies() -> None:
    clear_data()

    with TestSessionLocal() as database:
        thread = EmailThread(
            user_id=1,
            gmail_thread_id="analysis-thread-001",
            subject="Project deadline",
            snippet="Please submit the report by Friday.",
            participants="manager@example.com",
            message_count=1,
            latest_message_at=datetime.now(UTC),
        )

        database.add(thread)
        database.flush()

        analysis = ThreadAnalysis(
            thread_id=thread.id,
            model_name="test-model",
            source_fingerprint="a" * 64,
            summary="The sender requested the project report.",
            category="work",
            priority="high",
            sentiment="neutral",
        )

        analysis.action_items.append(
            ActionItem(
                title="Submit project report",
                description="Send the completed report to the manager.",
                owner="user@example.com",
                due_at=datetime(2030, 1, 4, tzinfo=UTC),
                priority="high",
            )
        )

        analysis.suggested_replies.append(
            SuggestedReply(
                tone="professional",
                subject="Re: Project deadline",
                body="I will send the completed report by Friday.",
            )
        )

        database.add(analysis)
        database.commit()
        database.refresh(analysis)

        assert analysis.id is not None
        assert analysis.thread.id == thread.id
        assert len(analysis.action_items) == 1
        assert len(analysis.suggested_replies) == 1
        assert analysis.action_items[0].title == ("Submit project report")
        assert analysis.suggested_replies[0].tone == "professional"
