FROM python:3.12-slim-bookworm

WORKDIR /app

# System deps for Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium --with-deps

COPY . .

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# SCRAPER_TARGET env var selects which scraper to run (e.g. autoscout24_de)
ENTRYPOINT ["python", "-m", "run_scraper"]
