"""Report which Monarch secrets exist in BWS and whether the MFA value is a
usable TOTP seed. Never prints secret values.

    python3 tools/check_secrets.py
"""
import json
import os
import subprocess
from urllib.parse import parse_qs, urlparse

BASE32 = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")


def mask(value: str) -> str:
    if "@" in value:
        return value[:3] + "..." + value.split("@")[-1]
    return f"{len(value)} chars"


def base32_ok(secret: str) -> bool:
    cleaned = secret.replace(" ", "").replace("-", "").rstrip("=").upper()
    return bool(cleaned) and set(cleaned) <= BASE32


def main() -> int:
    token = json.load(open(os.path.expanduser("~/.config/bws/config.json")))["access_token"]
    out = subprocess.run(
        ["bws", "secret", "list"], capture_output=True, text=True,
        env=dict(os.environ, BWS_ACCESS_TOKEN=token), timeout=60,
    )
    if out.returncode != 0:
        print("bws list failed:", out.stderr.strip()[:300])
        return 1
    secrets = {s.get("key"): s.get("value") for s in json.loads(out.stdout)}

    ok = True
    for key in ("monarch-email", "monarch-password", "monarch-mfa-secret"):
        value = secrets.get(key)
        if not value:
            print(f"{key:20} MISSING")
            ok = False
            continue
        if key == "monarch-email":
            print(f"{key:20} present, {mask(value)}")
        elif key == "monarch-password":
            print(f"{key:20} present, {len(value)} chars")
        else:
            if value.lower().startswith("otpauth://"):
                secret = (parse_qs(urlparse(value).query).get("secret") or [""])[0]
                label = urlparse(value).path.strip("/")
                print(f"{key:20} otpauth URI label={label} seed={len(secret)} chars "
                      f"base32={base32_ok(secret)}")
                ok = ok and base32_ok(secret)
            else:
                print(f"{key:20} raw seed {len(value)} chars base32={base32_ok(value)}")
                ok = ok and base32_ok(value)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
