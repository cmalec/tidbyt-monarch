"""Drive the scheduler without Monarch or a device: fake source, fake push.

Verifies push-on-change, that a push failure keeps the session and cache, and
that alerts fire at the threshold rather than every cycle.

    python -m tools.cycle_test
"""
import asyncio
import os
import sys

os.environ.update({
    "MONARCH_EMAIL": "selftest@example.invalid",
    "MONARCH_PASSWORD": "x",
    "TIDBYT_DEVICE_ID": "selftest",
    "TIDBYT_API_KEY": "k",
    "VIEWS": "dashboard",
    "UPDATE_INTERVAL": "180",
    "CACHE_TTL": "0",
    "GOTIFY_URL": "",
    "GOTIFY_TOKEN": "",
})

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import config, main as app_main  # noqa: E402

FRAME_DATA = {
    "networth": {"value": 1_786_495},
    "budget": {"pct": 75.7},
    "cashflow": {"rate": 0.218, "savings": 5325.54},
}

state = {"pushes": [], "alerts": [], "connects": 0, "fetch_fail": False,
         "push_fail": False, "data": FRAME_DATA}


class FakeSource:
    async def connect(self):
        state["connects"] += 1
        return "fake"

    async def dashboard(self):
        if state["fetch_fail"]:
            raise RuntimeError("session expired")
        return state["data"]

    async def close(self):
        return None


def reset(**overrides):
    state.update(pushes=[], alerts=[], connects=0, fetch_fail=False,
                 push_fail=False, data=FRAME_DATA)
    state.update(overrides)


async def fake_push(image, installation_id="monarch"):
    if state["push_fail"]:
        raise RuntimeError("tronbyt unreachable")
    state["pushes"].append(image)
    return {"status": 200, "body": "WebP received."}


def fake_alert(title, message, priority=5):
    state["alerts"].append((title, message))
    return True


async def drive(cycles: int):
    """Run the real scheduler for roughly `cycles` iterations, then stop."""
    task = asyncio.create_task(app_main._run())
    await asyncio.sleep(0.01 + cycles * config.UPDATE_INTERVAL * 1.5)
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):  # noqa: BLE001
        pass


def main() -> int:
    app_main.MonarchSource = lambda: FakeSource()
    app_main._push = fake_push
    app_main.notify.send = fake_alert
    app_main.notify.enabled = lambda: True
    config.VIEWS = ["dashboard"]
    config.UPDATE_INTERVAL = 0.02  # keep the harness fast
    config.ALERT_AFTER_FAILURES = 2
    config.ALERT_REPEAT_EVERY = 20

    failures = []

    def check(condition, message):
        if not condition:
            failures.append(message)

    # 1. identical frames push once, never alert, connect once
    reset()
    asyncio.run(drive(4))
    check(len(state["pushes"]) == 1,
          f"expected 1 push for identical frames, got {len(state['pushes'])}")
    check(not state["alerts"], f"healthy run alerted: {state['alerts']}")
    check(state["connects"] == 1, f"expected 1 connect, got {state['connects']}")

    # 2. changed data pushes again
    reset()
    asyncio.run(drive(2))
    state["data"] = {**FRAME_DATA, "networth": {"value": 1_800_000}}
    asyncio.run(drive(2))
    check(len(state["pushes"]) == 2, f"changed data should push twice, got {len(state['pushes'])}")

    # 3. fetch failures: one alert at the threshold, offline frame pushed once,
    #    session dropped so the next cycle reconnects
    reset(fetch_fail=True)
    asyncio.run(drive(5))
    check(len(state["alerts"]) == 1, f"expected exactly 1 alert, got {len(state['alerts'])}")
    check("session expired" in state["alerts"][0][1],
          f"alert lacked the reason: {state['alerts']}")
    check(len(state["pushes"]) == 1,
          f"offline frame should push once, got {len(state['pushes'])}")
    check(state["connects"] > 1, "session should be re-established after a fetch failure")

    # 4. push failures keep the session but still alert
    reset(push_fail=True)
    asyncio.run(drive(5))
    check(len(state["alerts"]) == 1,
          f"push failures should alert once, got {len(state['alerts'])}")
    check(state["connects"] == 1,
          f"push failure must not re-authenticate, connects={state['connects']}")

    # 5. a couple of push failures below the threshold stay quiet, then
    #    recovery pushes the new frame
    reset()
    config.ALERT_AFTER_FAILURES = 5
    asyncio.run(drive(2))
    state["push_fail"] = True
    asyncio.run(drive(2))
    check(len(state["alerts"]) == 0, f"below threshold should not alert: {state['alerts']}")
    state["push_fail"] = False
    state["data"] = {**FRAME_DATA, "networth": {"value": 1_900_000}}
    asyncio.run(drive(2))
    check(len(state["pushes"]) == 2,
          f"recovery should push the new frame, got {len(state['pushes'])} pushes")
    config.ALERT_AFTER_FAILURES = 2

    if failures:
        print(f"{len(failures)} failure(s):")
        for failure in failures:
            print("  FAIL", failure)
        return 1
    print("cycle test ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
