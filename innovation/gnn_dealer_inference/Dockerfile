FROM python:3.11-slim

WORKDIR /app

# Install CPU-only torch + PyG in one layer to minimise image size
RUN pip install --no-cache-dir \
        torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir \
        torch_geometric \
    && pip install --no-cache-dir \
        pyg_lib torch_scatter torch_sparse \
            -f https://data.pyg.org/whl/torch-$(python -c "import torch; v=torch.__version__; print(v.split('+')[0])")+cpu.html \
    || echo "WARNING: pyg_lib/torch_scatter/torch_sparse failed — some ops will be slower; DGL fallback available"

# Install remaining deps
COPY requirements.txt .
RUN pip install --no-cache-dir flask scikit-learn numpy

# Copy source
COPY *.py .

# Default: run serve.py
# Override with 'python train.py --db ...' for training
ENV GNN_PORT=8501
ENV GNN_MODEL_PATH=/data/model.pt
ENV GNN_DB_PATH=/data/discovery.db

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/health')"

CMD ["python", "serve.py"]
