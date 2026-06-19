FROM python:3.10-slim AS builder

WORKDIR /app
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt && \
    python -m playwright install chromium

FROM python:3.10-slim

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /root/.cache/ms-playwright /root/.cache/ms-playwright

RUN useradd -m appuser && \
    mkdir -p /app/data /app/logs && \
    chown -R appuser:appuser /app

COPY src/ src/
COPY config/ config/

ENV PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright

USER appuser

CMD ["python", "src/main.py"]
