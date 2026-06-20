FROM python:3.10-slim AS builder

WORKDIR /app
COPY requirements.txt .

ENV PLAYWRIGHT_BROWSERS_PATH=/app/browsers

RUN pip install --no-cache-dir -r requirements.txt && \
    python -m playwright install chromium

FROM python:3.10-slim

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /app/browsers /app/browsers

RUN python -m playwright install-deps chromium && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -m appuser && \
    mkdir -p /app/data /app/logs && \
    chown -R appuser:appuser /app

COPY src/ src/
COPY config/ config/

ENV PLAYWRIGHT_BROWSERS_PATH=/app/browsers
ENV PYTHONPATH=/app

USER appuser

CMD ["python", "-m", "src.main"]
