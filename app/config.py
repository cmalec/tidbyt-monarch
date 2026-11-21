"""Configuration loaded from environment variables, validated at import."""
import os

# --- Monarch credentials -------------------------------------------------
MONARCH_EMAIL = os.getenv("MONARCH_EMAIL", "")
MONARCH_PASSWORD = os.getenv("MONARCH_PASSWORD", "")


def _normalize_totp(raw: str) -> str:
    """Accept a base32 seed or an otpauth:// URI; reject anything unusable."""
    raw = (raw or "").strip()
    if not raw:
        return ""
    if raw.lower().startswith("otpauth://"):
        from urllib.parse import parse_qs, urlparse

        secret = (parse_qs(urlparse(raw).query).get("secret") or [""])[0]
        if not secret:
            raise ValueError(
                "MONARCH_MFA_SECRET looks like an otpauth:// URI but carries no "
                "secret= parameter"
            )
        raw = secret
    # base32 alphabet is A-Z and 2-7; spaces, dashes and padding are noise
    cleaned = raw.replace(" ", "").replace("-", "").rstrip("=").upper()
    if not cleaned or any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" for ch in cleaned):
        raise ValueError(
            "MONARCH_MFA_SECRET is not a base32 TOTP seed. Use the two-factor "
            "text code from Monarch Settings > Security, not a 6-digit code."
        )
    return cleaned


MONARCH_MFA_SECRET = _normalize_totp(os.getenv("MONARCH_MFA_SECRET", ""))

DATA_DIR = os.getenv("DATA_DIR", "/data")
MONARCH_SESSION_FILE = os.getenv("MONARCH_SESSION_FILE", os.path.join(DATA_DIR, "mm_session.pickle"))

# --- Push target ---------------------------------------------------------
TIDBYT_DEVICE_ID = os.getenv("TIDBYT_DEVICE_ID", "")
TIDBYT_API_KEY = os.getenv("TIDBYT_API_KEY", "")
# Tidbyt cloud by default; point at Tronbyt to stay local, e.g.
# http://tronbyt.local:8010/v0
TIDBYT_API_BASE = os.getenv("TIDBYT_API_BASE", "https://api.tidbyt.com/v0").rstrip("/")


# --- Behaviour -----------------------------------------------------------
def _int_env(name: str, default: int, minimum: int | None = None) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer, got: {raw!r}") from None
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be at least {minimum}, got: {value}")
    return value


ALL_VIEWS = ("dashboard", "networth", "budget", "goal", "cashflow", "bill")
VIEWS = [v.strip().lower() for v in os.getenv("VIEWS", "dashboard").split(",") if v.strip()]
_unknown = [v for v in VIEWS if v not in ALL_VIEWS]
if _unknown:
    raise ValueError(f"Unknown VIEWS entries: {_unknown}. Valid: {list(ALL_VIEWS)}")
if not VIEWS:
    raise ValueError("At least one entry is required in VIEWS")

# Each view stays on the panel this long.
UPDATE_INTERVAL = _int_env("UPDATE_INTERVAL", 180, minimum=10)

# How long fetched Monarch data is reused before hitting the API again.
# The panel refreshes far more often than the data changes; 3 hours keeps one
# login's worth of requests well clear of Monarch's rate limits.
CACHE_TTL = _int_env("CACHE_TTL", 10800, minimum=0)

# Which savings goal to show. Empty = first active goal, or set a goal id.
GOAL_ID = os.getenv("GOAL_ID", "")

# Which budget category the budget view shows. Empty = the month's totals.
# Matched case-insensitively against the category name.
BUDGET_CATEGORY = os.getenv("BUDGET_CATEGORY", "")

# Print the actual figures to the log. Off by default: the container log is
# not the place for net worth and bill amounts.
DEBUG_VALUES = os.getenv("DEBUG_VALUES", "").strip().lower() in ("1", "true", "yes", "on")

# Optional Gotify alerting: leave unset to disable.
GOTIFY_URL = os.getenv("GOTIFY_URL", "").strip()
GOTIFY_TOKEN = os.getenv("GOTIFY_TOKEN", "").strip()
if GOTIFY_URL and not GOTIFY_URL.startswith(("http://", "https://")):
    raise ValueError(
        f"GOTIFY_URL must start with http:// or https://, got: {GOTIFY_URL!r}. "
        "Inside a container a LAN address works, a tailnet name usually does not."
    )

# Consecutive failed cycles before alerting, and how often to repeat while
# still broken. One alert per incident, not one per cycle.
ALERT_AFTER_FAILURES = _int_env("ALERT_AFTER_FAILURES", 2, minimum=1)
ALERT_REPEAT_EVERY = _int_env("ALERT_REPEAT_EVERY", 20, minimum=0)

# --- Validation ----------------------------------------------------------
if not TIDBYT_DEVICE_ID:
    raise ValueError("TIDBYT_DEVICE_ID environment variable is required")
if not TIDBYT_API_KEY:
    raise ValueError("TIDBYT_API_KEY environment variable is required")
if not TIDBYT_API_BASE.startswith(("http://", "https://")):
    raise ValueError(
        f"TIDBYT_API_BASE must start with http:// or https://, got: {TIDBYT_API_BASE!r}"
    )
if not MONARCH_EMAIL:
    raise ValueError("MONARCH_EMAIL environment variable is required")
# A saved session can work without a password, but a cold start needs one.
if not MONARCH_PASSWORD and not os.path.exists(MONARCH_SESSION_FILE):
    raise ValueError(
        "MONARCH_PASSWORD is required for the first login "
        f"(no saved session at {MONARCH_SESSION_FILE})"
    )
