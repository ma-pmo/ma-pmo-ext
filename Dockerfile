# MA-PMO API image (FastAPI + LangGraph orchestration)
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    DB_URL=sqlite:///./data/ma_pmo.db \
    CHECKPOINT_DB=./data/ma_pmo_checkpoints.sqlite

# the package and its dependencies come from pyproject, so the image cannot drift from it
# (apps/web is a separate image -> excluded via .dockerignore)
COPY pyproject.toml README.md README.ko.md ./
COPY ma_pmo ./ma_pmo
RUN pip install --no-cache-dir ".[postgres,otel]"
COPY deploy/entrypoint.sh ./

RUN chmod +x entrypoint.sh && mkdir -p /app/data

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD python -c "import httpx,sys; sys.exit(0 if httpx.get('http://localhost:8000/health').status_code==200 else 1)"

CMD ["./entrypoint.sh"]
