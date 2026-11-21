"""Configuration loaded from environment variables."""
import os

# --- Monarch credentials -------------------------------------------------
MONARCH_EMAIL = os.getenv("MONARCH_EMAIL", "")
MONARCH_PASSWORD = os.getenv("MONARCH_PASSWORD", "")
# TOTP secret from Monarch Settings -> Security -> Enable MFA (the
# "two-factor text code"). Optional, but required for unattended re-login.
# Accepts either the raw base32 seed or an otpauth:// URI.
def _normalize_totp(raw: str) -> str:
    raw = (raw or "").strip()
    if raw.lower().startswith("otpauth://"):
        from urllib.parse import parse_qs, urlparse

        secret = (parse_qs(urlparse(raw).query).get("secret") or [""])[0]
        raw = secret
    # base32 alphabet is A-Z2-7; spaces and dashes are formatting noise
    return raw.replace(" ", "").replace("-", "").upper()


MONARCH_MFA_SECRET = _normalize_totp(os.getenv("MONARCH_MFA_SECRET", ""))

DATA_DIR = os.getenv("DATA_DIR", "/data")
MONARCH_SESSION_FILE = os.getenv("MONARCH_SESSION_FILE", os.path.join(DATA_DIR, "mm_session.pickle"))

# --- Push target ---------------------------------------------------------
TIDBYT_DEVICE_ID = os.getenv("TIDBYT_DEVICE_ID", "")
TIDBYT_API_KEY = os.getenv("TIDBYT_API_KEY", "")
# Tidbyt cloud by default; point at Tronbyt to stay local, e.g.
# http://192.168.1.77:8010/v0
TIDBYT_API_BASE = os.getenv("TIDBYT_API_BASE", "https://api.tidbyt.com/v0").rstrip("/")

# --- Behaviour -----------------------------------------------------------
_update_interval_raw = os.getenv("UPDATE_INTERVAL", "180")
try:
    UPDATE_INTERVAL = int(_update_interval_raw)
except ValueError:
    raise ValueError(f"UPDATE_INTERVAL must be an integer, got: {_update_interval_raw!r}")

ALL_VIEWS = ("dashboard", "networth", "budget", "goal", "cashflow", "bill")
VIEWS = [v.strip().lower() for v in os.getenv("VIEWS", "dashboard").split(",") if v.strip()]
_unknown = [v for v in VIEWS if v not in ALL_VIEWS]
if _unknown:
    raise ValueError(f"Unknown VIEWS entries: {_unknown}. Valid: {list(ALL_VIEWS)}")
if not VIEWS:
    raise ValueError("At least one entry is required in VIEWS")

# Which savings goal to show. Empty = first active goal, or set a goal id.
GOAL_ID = os.getenv("GOAL_ID", "")

# Which budget category the budget view shows. Empty = the month's totals.
BUDGET_CATEGORY = os.getenv("BUDGET_CATEGORY", "")

# How long fetched Monarch data is reused before hitting the API again.
# The panel refreshes much more often than the data changes; 3 hours keeps
# one login's worth of requests well clear of Monarch's rate limits.
_cache_ttl_raw = os.getenv("CACHE_TTL", "10800")
try:
    CACHE_TTL = int(_cache_ttl_raw)
except ValueError:
    raise ValueError(f"CACHE_TTL must be an integer number of seconds, got: {_cache_ttl_raw!r}")
if CACHE_TTL < 0:
    raise ValueError("CACHE_TTL must be zero or greater")

# Optional Gotify alerting: leave unset to disable.
GOTIFY_URL = os.getenv("GOTIFY_URL", "")
GOTIFY_TOKEN = os.getenv("GOTIFY_TOKEN", "")

# Consecutive failed cycles before alerting, and how often to repeat while
# still broken. One alert per incident, not one per cycle.
ALERT_AFTER_FAILURES = int(os.getenv("ALERT_AFTER_FAILURES", "2"))
ALERT_REPEAT_EVERY = int(os.getenv("ALERT_REPEAT_EVERY", "20"))

# Number of months of history for the cashflow view.
CASHFLOW_MONTHS = int(os.getenv("CASHFLOW_MONTHS", "1"))

# --- Validation ----------------------------------------------------------
if not TIDBYT_DEVICE_ID:
    raise ValueError("TIDBYT_DEVICE_ID environment variable is required")
if not TIDBYT_API_KEY:
    raise ValueError("TIDBYT_API_KEY environment variable is required")
if not MONARCH_EMAIL:
    raise ValueError("MONARCH_EMAIL environment variable is required")
# A saved session can work without a password, but a cold start needs one.
if not MONARCH_PASSWORD and not os.path.exists(MONARCH_SESSION_FILE):
    raise ValueError(
        "MONARCH_PASSWORD is required for the first login "
        f"(no saved session at {MONARCH_SESSION_FILE})"
    )
