# syntax=docker/dockerfile:1

FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

COPY pyproject.toml ./
COPY app ./app

RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install .

FROM python:3.12-slim AS runtime

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONPATH="/app" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN groupadd --system --gid 10001 inbox2done \
    && useradd \
        --system \
        --uid 10001 \
        --gid inbox2done \
        --home-dir /app \
        --shell /usr/sbin/nologin \
        inbox2done

COPY --from=builder /opt/venv /opt/venv
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

RUN chown -R inbox2done:inbox2done /app

USER inbox2done

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
