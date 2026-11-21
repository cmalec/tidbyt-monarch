FROM python:3.11-slim-bookworm

WORKDIR /app

# tzdata: without it TZ=... silently falls back to UTC on slim images, which
# shifts "today" and month boundaries. gosu: drop root after fixing the volume.
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu \
    tzdata \
    gosu \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Runtime only. tools/ and tests/ stay out of the published image.
COPY app/ ./app/
COPY entrypoint.sh /entrypoint.sh
RUN chmod 0755 /entrypoint.sh && mkdir -p /data

ENV PYTHONUNBUFFERED=1
ENV DATA_DIR=/data
ENV UPDATE_INTERVAL=180
ENV VIEWS=dashboard
ENV CACHE_TTL=10800
ENV GOTIFY_URL=
ENV GOTIFY_TOKEN=
ENV TIDBYT_API_BASE=https://api.tidbyt.com/v0
ENV PUID=99
ENV PGID=100
ENV TZ=America/Los_Angeles

# starts as root only to take ownership of /data, then execs as PUID:PGID
ENTRYPOINT ["/entrypoint.sh"]
