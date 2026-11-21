"""Report which Monarch secrets exist in BWS, and whether the MFA value is a
raw base32 seed or an otpauth:// URI. Never prints secret values."""
import json, os, subprocess
from urllib.parse import urlparse, parse_qs

TOKEN = json.load(open(os.path.expanduser("~/.config/bws/config.json")))["access_token"]
out = subprocess.run(["bws", "secret", "list"], capture_output=True, text=True,
                     env=dict(os.environ, BWS_ACCESS_TOKEN=TOKEN), timeout=60)
secrets = {s.get("key"): s.get("value") for s in json.loads(out.stdout)}

wanted = ["monarch-email", "monarch-password", "monarch-mfa-secret"]
for key in wanted:
    val = secrets.get(key)
    if val is None:
        print(f"{key:20} MISSING")
        continue
    if key == "monarch-email":
        masked = val[:3] + "..." + val.split("@")[-1] if "@" in val else "(no @)"
        print(f"{key:20} present, looks like {masked}")
    elif key == "monarch-password":
        print(f"{key:20} present, {len(val)} chars")
    else:
        if val.lower().startswith("otpauth://"):
            q = parse_qs(urlparse(val).query)
            secret = (q.get("secret") or [""])[0]
            label = urlparse(val).path.strip("/")
            print(f"{key:20} otpauth URI, label={label}, secret len={len(secret)}, base32 alphabet={all(c.isalnum() for c in secret)}")
        else:
            print(f"{key:20} raw value, len={len(val)}, base32 alphabet={all(c.isalnum() for c in val)}")
