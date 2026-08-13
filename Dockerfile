FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/TianMingYo/Camp_Harness"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY demo ./demo
RUN python -m pip install --no-cache-dir .

EXPOSE 8000
CMD ["sh", "-c", "exec python -m uvicorn feedbackloop.api:demo_app --host 0.0.0.0 --port \"${PORT:-8000}\""]
