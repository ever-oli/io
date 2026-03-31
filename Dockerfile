FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    IO_HOME=/root/.io \
    UV_LINK_MODE=copy

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.7.22 /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY packages ./packages

RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:${PATH}"

VOLUME ["/root/.io", "/workspace"]

ENTRYPOINT ["io"]
CMD ["status", "--pretty"]
