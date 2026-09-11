FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN useradd -m appuser && \
    mkdir -p /app/data /app/logs && \
    chown -R appuser:appuser /app

COPY src/ src/
COPY config/ config/

ENV PYTHONPATH=/app

USER appuser

CMD ["python", "-m", "src.main"]
