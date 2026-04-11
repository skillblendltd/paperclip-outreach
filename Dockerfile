FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# System deps: psycopg2 build tools + cron + curl + Chromium runtime libs
# (Chromium deps are manual because `playwright install --with-deps` requires
# ttf-unifont which isn't in Debian Bookworm.)
RUN apt-get update -qq && \
    apt-get install -y -qq --no-install-recommends \
        libpq-dev \
        gcc \
        cron \
        curl \
        ca-certificates \
        libnss3 \
        libnspr4 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libcups2 \
        libdrm2 \
        libxkbcommon0 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxrandr2 \
        libgbm1 \
        libpango-1.0-0 \
        libcairo2 \
        libasound2 \
        fonts-liberation \
        fonts-noto-color-emoji && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium binary (system libs already provided above)
RUN playwright install chromium

COPY . .

EXPOSE 8002

CMD ["python", "manage.py", "runserver", "0.0.0.0:8002"]
