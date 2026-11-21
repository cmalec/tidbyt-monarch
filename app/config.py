"""Configuration loaded from environment variables."""
import os

# --- Monarch credentials -------------------------------------------------
MONARCH_EMAIL = os.getenv("MONARCH_EMAIL", "")
MONARCH_PASSWORD = os.getenv("MONARCH_PASSWORD", "")
# TOTP secret from Monarch Settings -> Security -> Enable MFA (the
# "two-factor text code"). Optional, but required for unattended re-login.
MONARCH_MFA_SECRET = os.getenv("MONARCH_MFA_SECRET", "").replace(" ", "")

DATA_DIR = os.getenv("DATA_DIR", "/data")
MONARCH_SESSION_FILE = os.getenv("MONARCH_SESSION_FILE", os.path.join(DATA_DIR, "mm_session.pickle"))

# --- Push target ---------------------------------------------------------
TIDBYT_DEVICE_ID = os.getenv("TIDBYT_DEVICE_ID", "")
TIDBYT_API_KEY = os.getenv("TIDBYT_API_KEY", "")
# Tidbyt cloud by default; point at Tronbyt to stay local, e.g.
# http://192.168.1.77:8010/v0
TIDBYT_API_BASE = os.getenv("TIDBYT_API_BASE", "https://api.tidbyt.com/v0").rstrip("/")

# --- Behaviour -----------------------------------------------------------
_update_interval_raw = os.getenv("UPDATE_INTERVAL", "60")
try:
    UPDATE_INTERVAL = int(_update_interval_raw)
except ValueError:
    raise ValueError(f"UPDATE_INTERVAL must be an integer, got: {_update_interval_raw!r}")

ALL_VIEWS = ("networth", "goal", "cashflow", "bill")
VIEWS = [v.strip().lower() for v in os.getenv("VIEWS", "networth,goal,cashflow,bill").split(",") if v.strip()]
_unknown = [v for v in VIEWS if v not in ALL_VIEWS]
if _unknown:
    raise ValueError(f"Unknown VIEWS entries: {_unknown}. Valid: {list(ALL_VIEWS)}")
if not VIEWS:
    raise ValueError("At least one entry is required in VIEWS")

# Which savings goal to show. Empty = first active goal, or set a goal id.
GOAL_ID = os.getenv("GOAL_ID", "")

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
