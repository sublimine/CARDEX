FROM python:3.12-slim-bookworm

WORKDIR /app/scrapers

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

WORKDIR /app/scrapers

# Default: single scraper via SCRAPER_TARGET.
# Override CMD in docker-compose for multi-scraper mode with run_all.
ENTRYPOINT ["python"]
CMD ["-m", "run_scraper"]
