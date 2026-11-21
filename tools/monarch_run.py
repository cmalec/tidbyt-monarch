"""Run a module inside the local image with credentials from Bitwarden
Secrets Manager.

    python3 tools/monarch_run.py app.live
"""
import json
import os
import subprocess
import sys
import tempfile

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
    module = sys.argv[1] if len(sys.argv) > 1 else "app.dump"
    found = list_secrets()
    for key in ("monarch-email", "monarch-password"):
        if not found.get(key):
            raise SystemExit(f"missing BWS secret: {key}")

    os.makedirs(f"{REPO}/data", exist_ok=True)
    os.makedirs(f"{REPO}/preview", exist_ok=True)
    env_lines = [
        f"MONARCH_EMAIL={found['monarch-email']}",
        f"MONARCH_PASSWORD={found['monarch-password']}",
        f"MONARCH_MFA_SECRET={found.get('monarch-mfa-secret') or ''}",
        f"TIDBYT_DEVICE_ID={os.environ.get('TRONBYT_DEVICE', 'pixelnode')}",
        f"TIDBYT_API_KEY={os.environ.get('TRONBYT_KEY', 'unused-for-preview')}",
        f"TIDBYT_API_BASE={os.environ.get('TRONBYT_URL', 'https://api.tidbyt.com/v0')}",
        "DATA_DIR=/data",
    ]
    for extra in sys.argv[2:]:
        env_lines.append(extra)

    fd, path = tempfile.mkstemp(prefix="monarch-env-", suffix=".env")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write("\n".join(env_lines) + "\n")
        os.chmod(path, 0o600)
        cmd = [
            "docker", "run", "--rm",
            "--user", f"{os.getuid()}:{os.getgid()}",
            "-v", f"{REPO}/data:/data",
            "-v", f"{REPO}/preview:/out",
            "--env-file", path,
            "--entrypoint", "python",
            "tidbyt-monarch:local", "-m", module,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    finally:
        os.unlink(path)

    print(r.stdout[-6000:])
    if r.returncode != 0:
        print("STDERR:", r.stderr[-2000:])


if __name__ == "__main__":
    main()
