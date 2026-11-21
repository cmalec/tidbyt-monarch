FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY tools/ ./tools/

# The Monarch session file lives here; mount it to keep logins.
RUN mkdir -p /data

ENV PYTHONUNBUFFERED=1
ENV DATA_DIR=/data
ENV UPDATE_INTERVAL=180
ENV VIEWS=dashboard
ENV CACHE_TTL=10800
ENV GOTIFY_URL=
ENV GOTIFY_TOKEN=
ENV TIDBYT_API_BASE=https://api.tidbyt.com/v0
ENV TZ=America/Los_Angeles

CMD ["python", "-m", "app.main"]
