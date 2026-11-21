"""Run the notify test in the local image with the Gotify token from BWS."""
import json
import os
import subprocess
import tempfile

REPO = "/home/claw/code/tidbyt-monarch"
TOKEN = json.load(open(os.path.expanduser("~/.config/bws/config.json")))["access_token"]

out = subprocess.run(
    ["bws", "secret", "list"], capture_output=True, text=True,
    env=dict(os.environ, BWS_ACCESS_TOKEN=TOKEN), timeout=60,
)
secrets = {s.get("key"): s.get("value") for s in json.loads(out.stdout)}
gotify = secrets.get("gotify-token")
if not gotify:
    raise SystemExit("no gotify-token in BWS")

env_lines = [
    "MONARCH_EMAIL=t@example.invalid",
    "MONARCH_PASSWORD=x",
    "TIDBYT_DEVICE_ID=pixelnode",
    "TIDBYT_API_KEY=k",
    "GOTIFY_URL=http://192.168.1.77:8070",
    f"GOTIFY_TOKEN={gotify}",
]
fd, path = tempfile.mkstemp(prefix="gotify-env-", suffix=".env")
try:
    with os.fdopen(fd, "w") as fh:
        fh.write("\n".join(env_lines) + "\n")
    os.chmod(path, 0o600)
    r = subprocess.run(
        ["docker", "run", "--rm", "--env-file", path, "--entrypoint", "python",
         "tidbyt-monarch:local", "-m", "tools.notify_test"],
        capture_output=True, text=True, timeout=180,
    )
finally:
    os.unlink(path)

print(r.stdout.strip())
if r.returncode != 0:
    print("stderr:", r.stderr[-500:])
