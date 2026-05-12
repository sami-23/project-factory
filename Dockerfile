FROM python:3.12-bookworm

# Node.js (for JS projects)
RUN apt-get update && apt-get install -y curl gnupg && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright + Chromium
RUN playwright install chromium --with-deps

COPY . .

# Data dir (override with a Railway volume at /data)
RUN mkdir -p data/screenshots

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
