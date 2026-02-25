FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PUPPETEER_SKIP_DOWNLOAD=1

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ca-certificates \
      chromium \
      fonts-noto \
      fonts-noto-color-emoji \
      nodejs \
      npm && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements.txt
RUN python -m pip install --upgrade pip && \
    python -m pip install --no-cache-dir -r requirements.txt

COPY reports/pdf_renderer/package.json reports/pdf_renderer/package-lock.json reports/pdf_renderer/
RUN cd reports/pdf_renderer && npm ci --omit=dev --no-audit --no-fund

COPY . .

EXPOSE 8000
