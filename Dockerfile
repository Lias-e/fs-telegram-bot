FROM python:3.10-slim AS builder

WORKDIR /app
COPY requirements.txt .

RUN pip install --user --no-cache-dir -r requirements.txt && \
    python -m playwright install chromium

FROM python:3.10-slim

WORKDIR /app

RUN useradd -m appuser && \
    mkdir -p /app/data /app/logs && \
    chown -R appuser:appuser /app

COPY --from=builder /root/.local /root/.local
COPY --from=builder /root/.cache/ms-playwright /root/.cache/ms-playwright

COPY src/ src/
COPY config/ config/

ENV PATH="/root/.local/bin:${PATH}"
ENV PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright

USER appuser

CMD ["python", "src/main.py"]
