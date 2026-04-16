FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY data_pipeline.py forecaster.py forecast_all.py serve.py ./

ENV TIMESERIES_DIR=/data/timeseries \
    FORECAST_PORT=8503 \
    CHRONOS_MODEL=amazon/chronos-bolt-mini

EXPOSE 8503

VOLUME ["/data/timeseries"]

CMD ["uvicorn", "serve:app", "--host", "0.0.0.0", "--port", "8503"]
