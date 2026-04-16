FROM python:3.11-slim

WORKDIR /app

# System dependencies for FAISS and sentence-transformers
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Pre-download nomic-embed-text model at build time so the container starts fast.
# The model is cached in HF_HOME (/root/.cache/huggingface).
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('nomic-ai/nomic-embed-text-v1.5', trust_remote_code=True)"

# Data volumes
VOLUME ["/app/data", "/app/models"]

EXPOSE 8502

ENV RAG_DATA_DIR=/app/data/rag \
    CARDEX_DB_PATH=/app/data/discovery.db \
    RAG_API_PORT=8502 \
    RAG_LLM_RERANK=false

CMD ["uvicorn", "serve:app", "--host", "0.0.0.0", "--port", "8502"]
