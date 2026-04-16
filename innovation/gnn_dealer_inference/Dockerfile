FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libsqlite3-0 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    torch --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir \
    torch_geometric flask scikit-learn numpy

RUN pip install --no-cache-dir pyg_lib torch_scatter torch_sparse \
    -f https://data.pyg.org/whl/torch-$(python -c "import torch; print(torch.__version__.split('+')[0])")+cpu.html \
    || echo "WARNING: torch_scatter/torch_sparse unavailable — using DGL fallback"

COPY . .

ENV GNN_PORT=8501
EXPOSE 8501

CMD ["python", "serve.py"]
