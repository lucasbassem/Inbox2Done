from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy import StaticPool, create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.action_item import ActionItem
from app.models.email_message import EmailMessage
from app.models.email_thread import EmailThread
from app.models.suggested_reply import SuggestedReply
from app.models.thread_analysis import ThreadAnalysis
from app.schemas.analysis import (
    GeneratedActionItem,
    GeneratedSuggestedReply,
    GeneratedThreadAnalysis,
)
from app.services.thread_analysis import (
    analyze_thread,
    build_thread_fingerprint,
)

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


class FakeResponses:
    def __init__(
        self,
        generated: GeneratedThreadAnalysis,
    ) -> None:
        self.generated = generated
        self.call_count = 0

    def parse(self, **_kwargs):
        self.call_count += 1

        return SimpleNamespace(
            output_parsed=self.generated,
        )


class FakeOpenAI:
    def __init__(
        self,
        generated: GeneratedThreadAnalysis,
    ) -> None:
        self.responses = FakeResponses(generated)


def clear_data() -> None:
    with TestSessionLocal() as database:
        database.query(ActionItem).delete()
        database.query(SuggestedReply).delete()
        database.query(ThreadAnalysis).delete()
        database.query(EmailMessage).delete()
        database.query(EmailThread).delete()
        database.commit()


def create_thread() -> int:
    with TestSessionLocal() as database:
        thread = EmailThread(
            user_id=1,
            gmail_thread_id="openai-thread-001",
            subject="Submit project report",
            snippet="Please submit the report by Friday.",
            participants="manager@example.com",
            message_count=1,
            latest_message_at=datetime.now(UTC),
        )

        database.add(thread)
        database.flush()

        database.add(
            EmailMessage(
                thread_id=thread.id,
                gmail_message_id="openai-message-001",
                sender="Manager <manager@example.com>",
                recipients="employee@example.com",
                subject="Submit project report",
                snippet="Please submit the report by Friday.",
                body_text=("Please send the final project report by Friday at 5 PM."),
                sent_at=datetime(2030, 1, 1, 12, 0, tzinfo=UTC),
            )
        )

        database.commit()

        return thread.id


def generated_analysis() -> GeneratedThreadAnalysis:
    return GeneratedThreadAnalysis(
        summary="The manager requested the final report by Friday.",
        category="work",
        priority="high",
        sentiment="neutral",
        action_items=[
            GeneratedActionItem(
                title="Submit final project report",
                description="Send the final report to the manager.",
                owner="employee@example.com",
                due_at=datetime(2030, 1, 4, 17, 0, tzinfo=UTC),
                priority="high",
            )
        ],
        suggested_replies=[
            GeneratedSuggestedReply(
                tone="professional",
                subject="Re: Submit project report",
                body="I will send the final report by Friday at 5 PM.",
            )
        ],
    )


def test_thread_fingerprint_is_deterministic() -> None:
    clear_data()
    thread_id = create_thread()

    with TestSessionLocal() as database:
        thread = database.get(EmailThread, thread_id)

        assert thread is not None

        first = build_thread_fingerprint(thread)
        second = build_thread_fingerprint(thread)

    assert first == second
    assert len(first) == 64


def test_analysis_is_persisted() -> None:
    clear_data()
    thread_id = create_thread()
    fake_client = FakeOpenAI(generated_analysis())

    with TestSessionLocal() as database:
        analysis = analyze_thread(
            database=database,
            thread_id=thread_id,
            client=fake_client,
        )

        action_count = database.scalar(select(func.count()).select_from(ActionItem))
        reply_count = database.scalar(select(func.count()).select_from(SuggestedReply))

        assert analysis.summary == ("The manager requested the final report by Friday.")
        assert analysis.priority == "high"
        assert action_count == 1
        assert reply_count == 1
        assert analysis.action_items[0].title == ("Submit final project report")
        assert analysis.suggested_replies[0].tone == "professional"

    assert fake_client.responses.call_count == 1


def test_unchanged_thread_reuses_existing_analysis() -> None:
    clear_data()
    thread_id = create_thread()
    fake_client = FakeOpenAI(generated_analysis())

    with TestSessionLocal() as database:
        first = analyze_thread(
            database=database,
            thread_id=thread_id,
            client=fake_client,
        )

        second = analyze_thread(
            database=database,
            thread_id=thread_id,
            client=fake_client,
        )

        analysis_count = database.scalar(select(func.count()).select_from(ThreadAnalysis))

        assert first.id == second.id
        assert analysis_count == 1

    assert fake_client.responses.call_count == 1
