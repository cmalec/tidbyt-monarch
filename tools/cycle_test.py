"""Exercise the scheduler without Monarch or a device: fake source, fake push,
bounded cycles. Verifies push-on-change and the alert threshold."""
import sys

sys.path.insert(0, "/app")

import app.main as m  # noqa: E402
from app import config  # noqa: E402

FRAME_DATA = {
    "networth": {"value": 1_786_495.0},
    "budget": {"name": "TOTAL", "planned": 24993, "actual": 18915, "pct": 75.68},
    "cashflow": {"income": 24416.83, "expense": 19091.29, "savings": 5325.54, "rate": 0.218},
}

state = {"pushes": [], "alerts": [], "cycles": 0, "fail": False}


class FakeSource:
    async def connect(self):
        return "fake"

    async def dashboard(self):
        if state["fail"]:
            raise RuntimeError("session expired")
        return FRAME_DATA


def fake_push(image, installation_id="monarch"):
    state["pushes"].append(image)
    return {"status": 200, "body": "WebP received."}


def fake_alert(title, message, priority=5):
    state["alerts"].append((title, message))
    return True


def fake_sleep(_seconds):
    state["cycles"] += 1
    if state["cycles"] >= 3:
        raise SystemExit(0)


m.MonarchSource = FakeSource
m.push_image = fake_push
m.notify.send = fake_alert
m.notify.enabled = lambda: True
m.time.sleep = fake_sleep
config.VIEWS = ["dashboard"]
config.UPDATE_INTERVAL = 0
config.ALERT_AFTER_FAILURES = 2
config.ALERT_REPEAT_EVERY = 20

try:
    m.main()
except SystemExit:
    pass

print(f"\nunchanged-data run: {len(state['pushes'])} push(es), {len(state['alerts'])} alert(s)")
assert len(state["pushes"]) == 1, f"expected 1 push for identical frames, got {len(state['pushes'])}"
assert not state["alerts"], "should not alert when healthy"

# now break the source: 3 failing cycles, threshold is 2
state.update(pushes=[], alerts=[], cycles=0, fail=True)
try:
    m.main()
except SystemExit:
    pass

print(f"failing run: {len(state['pushes'])} push(es), {len(state['alerts'])} alert(s)")
assert len(state["alerts"]) == 1, f"expected exactly 1 alert at threshold, got {len(state['alerts'])}"
assert "session expired" in state["alerts"][0][1]
assert len(state["pushes"]) == 1, "offline frame should be pushed once, not every cycle"
print("cycle ok")
