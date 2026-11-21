#!/bin/sh
# Drop privileges before running the app. Unraid bind mounts are owned by
# nobody:users (99:100) by default, so the container needs to hand ownership
# over once and then run as that user rather than as root.
set -e

PUID="${PUID:-99}"
PGID="${PGID:-100}"
DATA_DIR="${DATA_DIR:-/data}"

if [ "$(id -u)" = "0" ]; then
    mkdir -p "$DATA_DIR"
    # only when needed: recursive chown on every start is slow on big volumes
    owner="$(stat -c '%u:%g' "$DATA_DIR" 2>/dev/null || echo '')"
    if [ "$owner" != "$PUID:$PGID" ]; then
        chown -R "$PUID:$PGID" "$DATA_DIR" 2>/dev/null || true
    fi
    exec gosu "$PUID:$PGID" python -m app.main
fi

exec python -m app.main
