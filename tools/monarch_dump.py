"""Read Monarch credentials from Bitwarden Secrets Manager and run the payload
dump inside the locally built image, so field shapes are verified before
anything is deployed.

Usage: python3 tools/monarch_dump.py
"""
import json
import os
import subprocess
import tempfile

BWS_KEYS = {
    "MONARCH_EMAIL": "monarch-email",
    "MONARCH_PASSWORD": "monarch-password",
    "MONARCH_MFA_SECRET": "monarch-mfa-secret",
}
REPO = "/home/claw/code/tidbyt-monarch"

TOKEN = json.load(open(os.path.expanduser("~/.config/bws/config.json")))["access_token"]


def list_secrets():
    out = subprocess.run(
        ["bws", "secret", "list"], capture_output=True, text=True,
        env=dict(os.environ, BWS_ACCESS_TOKEN=TOKEN), timeout=60,
    )
    if out.returncode != 0:
        raise SystemExit(f"bws list failed: {out.stderr[:200]}")
    return {s.get("key"): s.get("value") for s in json.loads(out.stdout)}


def main():
    found = list_secrets()
    missing = [k for k in BWS_KEYS.values() if not found.get(k)]
    if missing:
        print("missing BWS secrets:", missing)
        print("available keys:", sorted(k for k in found if k))
        raise SystemExit(1)

    os.makedirs(f"{REPO}/data", exist_ok=True)
    env_lines = [
        f"MONARCH_EMAIL={found['monarch-email']}",
        f"MONARCH_PASSWORD={found['monarch-password']}",
        f"MONARCH_MFA_SECRET={found.get('monarch-mfa-secret') or ''}",
        "TIDBYT_DEVICE_ID=pixelnode",
        "TIDBYT_API_KEY=unused-for-dump",
        "DATA_DIR=/data",
    ]
    # env file keeps secrets out of the process list
    fd, path = tempfile.mkstemp(prefix="monarch-env-", suffix=".env")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write("\n".join(env_lines) + "\n")
        os.chmod(path, 0o600)
        cmd = [
            "docker", "run", "--rm",
            "-v", f"{REPO}/data:/data",
            "--env-file", path,
            "--entrypoint", "python",
            "tidbyt-monarch:local", "-m", "app.inspect3",
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    finally:
        os.unlink(path)

    print(r.stdout[-6000:])
    if r.returncode != 0:
        print("STDERR:", r.stderr[-1500:])


if __name__ == "__main__":
    main()
