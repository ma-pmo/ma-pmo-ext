# MA-PMO API image (FastAPI + LangGraph orchestration)
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    DB_URL=sqlite:///./data/ma_pmo.db \
    CHECKPOINT_DB=./data/ma_pmo_checkpoints.sqlite

# runtime dependencies (kept in sync with pyproject; the package runs from source)
RUN pip install --no-cache-dir \
    "langgraph>=0.2.60" "langgraph-checkpoint-sqlite>=2.0.0" \
    "pydantic>=2.7" "pydantic-settings>=2.3" "litellm>=1.55" \
    "fastapi>=0.115" "uvicorn[standard]>=0.30" "sqlalchemy>=2.0" \
    "structlog>=24.1" "python-dotenv>=1.0" "httpx>=0.27" "psycopg[binary]>=3.2"

# application source (apps/web is a separate image -> excluded via .dockerignore)
COPY ma_pmo ./ma_pmo
COPY README.md README.ko.md deploy/entrypoint.sh ./

RUN chmod +x entrypoint.sh && mkdir -p /app/data

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD python -c "import httpx,sys; sys.exit(0 if httpx.get('http://localhost:8000/health').status_code==200 else 1)"

CMD ["./entrypoint.sh"]
