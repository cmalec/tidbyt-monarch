"""Offline self-test suite: no Monarch account, no device, no network.

    python -m tools.selftest

Every check here is deterministic. Anything needing live credentials belongs
in tools/monarch_run.py, not in CI.
"""
import io
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# config validates at import, so satisfy it before importing app modules
os.environ.update({
    "MONARCH_EMAIL": "selftest@example.invalid",
    "MONARCH_PASSWORD": "x",
    "TIDBYT_DEVICE_ID": "pixel node/1",
    "TIDBYT_API_KEY": "dev-key",
    "TIDBYT_API_BASE": "http://127.0.0.1:18030/v0",
    "VIEWS": "dashboard",
    "UPDATE_INTERVAL": "180",
    "CACHE_TTL": "10800",
    "GOTIFY_URL": "",
    "GOTIFY_TOKEN": "",
})

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402

from app import config, main as app_main, notify, push_client  # noqa: E402
from app.monarch_client import MonarchSource, _looks_like_auth_error  # noqa: E402
from app.renderer import (  # noqa: E402
    COLOR_NEG,
    COLOR_POS,
    COLOR_TEXT,
    compact_money,
    dashboard_fit_report,
    money,
    render,
    render_error,
)

FAILURES = []


def check(name, fn):
    try:
        fn()
    except AssertionError as exc:
        FAILURES.append(f"{name}: {exc}")
    except Exception as exc:  # noqa: BLE001
        FAILURES.append(f"{name}: unexpected {type(exc).__name__}: {exc}")


def expect(condition, message):
    if not condition:
        raise AssertionError(message)


# --- currency -------------------------------------------------------------
def test_money():
    cases = {
        None: "n/a",
        0: "$0",
        -0.4: "$0",
        999.4: "$999",
        999.6: "$1.0K",
        1_000: "$1.0K",
        8_200: "$8.2K",
        9_949: "$9.9K",
        9_950: "$10K",
        42_000: "$42K",
        412_345: "$412K",
        999_400: "$999K",
        999_500: "$1.0M",
        1_234_567: "$1.23M",
        1_240_000: "$1.24M",
        12_400_000: "$12.4M",
        -412_345: "-$412K",
        float("nan"): "n/a",
        float("inf"): "n/a",
    }
    for value, want in cases.items():
        got = money(value)
        expect(got == want, f"money({value!r}) = {got!r}, want {want!r}")


def test_compact_money():
    cases = {
        None: "n/a",
        999.6: "$1.0K",
        9_950: "$10K",
        999_500: "$1.0M",
        1_786_495: "$1.8M",
        -3900: "-$3.9K",
        5_325.54: "$5.3K",
    }
    for value, want in cases.items():
        got = compact_money(value)
        expect(got == want, f"compact_money({value!r}) = {got!r}, want {want!r}")


# --- dashboard ------------------------------------------------------------
GOOD = {
    "networth": {"value": 1_786_495},
    "budget": {"pct": 75.7},
    "cashflow": {"rate": 0.218, "savings": 5325.54},
}
EMPTY = {
    "networth": {"value": None},
    "budget": {"pct": None},
    "cashflow": {"rate": None, "savings": None},
}
OVER = {
    "networth": {"value": -1_234_567},
    "budget": {"pct": 145.0},
    "cashflow": {"rate": -0.48, "savings": -3900},
}

CELLS = {"NW": (0, 0), "BUD": (32, 0), "SAVE": (0, 16), "CF": (32, 16)}


def _cell_colors(data):
    img = Image.open(io.BytesIO(render("dashboard", data))).convert("RGB")
    px = img.load()
    out = {}
    for cell, (x0, y0) in CELLS.items():
        counts = {}
        for y in range(y0 + 6, y0 + 16):
            for x in range(x0, x0 + 32):
                colour = px[x, y]
                if colour != (0, 0, 0):
                    counts[colour] = counts.get(colour, 0) + 1
        out[cell] = max(counts, key=counts.get) if counts else None
    return out


def test_dashboard_fit():
    for label, data in (("good", GOOD), ("empty", EMPTY), ("over", OVER)):
        problems = dashboard_fit_report(data)
        expect(not problems, f"{label}: {problems}")


def test_dashboard_edges():
    """No lit pixel may touch the frame border for any grid state."""
    for label, data in (("good", GOOD), ("empty", EMPTY), ("over", OVER)):
        img = Image.open(io.BytesIO(render("dashboard", data))).convert("RGB")
        px = img.load()
        for x in (0, img.width - 1):
            expect(all(px[x, y] == (0, 0, 0) for y in range(img.height)),
                   f"{label}: lit pixel on column {x}")
        for y in (0, img.height - 1):
            expect(all(px[x, y] == (0, 0, 0) for x in range(img.width)),
                   f"{label}: lit pixel on row {y}")


def test_dashboard_colors():
    import math

    def near(colour, want):
        return colour is not None and sum(abs(a - b) for a, b in zip(colour, want)) < 90

    expect(near(_cell_colors(GOOD)["NW"], COLOR_POS), "good NW should be green")
    expect(near(_cell_colors(GOOD)["CF"], COLOR_POS), "good CF should be green")
    expect(near(_cell_colors(OVER)["NW"], COLOR_NEG), "negative NW should be red")
    expect(near(_cell_colors(OVER)["BUD"], COLOR_NEG), "over budget should be red")

    empty = _cell_colors(EMPTY)
    for cell, colour in empty.items():
        expect(near(colour, COLOR_TEXT), f"{cell} with no data should be neutral, was {colour}")
        expect(not math.isnan(1), "sanity")


def test_error_frame():
    frame = render_error("ConnectionResetError: something very long " * 3)
    img = Image.open(io.BytesIO(frame)).convert("RGB")
    px = img.load()
    for x in (0, img.width - 1):
        expect(all(px[x, y] == (0, 0, 0) for y in range(img.height)),
               f"error frame lit column {x}")


# --- scheduler ------------------------------------------------------------
def test_alert_schedule():
    original = (config.ALERT_AFTER_FAILURES, config.ALERT_REPEAT_EVERY)
    try:
        cases = {
            (2, 20): [2, 22, 42],
            (5, 3): [5, 8, 11, 14],
            (1, 0): [1],
            (3, 0): [3],
        }
        for (after, repeat), want in cases.items():
            config.ALERT_AFTER_FAILURES, config.ALERT_REPEAT_EVERY = after, repeat
            got = [n for n in range(1, 50) if app_main._should_alert(n)]
            expect(got[:len(want)] == want,
                   f"after={after} repeat={repeat}: got {got[:len(want)]}, want {want}")
            if repeat > 0:
                expect(all(n >= after for n in got),
                       f"after={after} repeat={repeat}: alerted before the threshold")
    finally:
        config.ALERT_AFTER_FAILURES, config.ALERT_REPEAT_EVERY = original


def test_safe_detail():
    text = app_main._safe_detail(RuntimeError("token=abcdef0123456789abcdef0123456789"))
    expect("abcdef0123456789" not in text, f"secret not redacted: {text}")


# --- parsers --------------------------------------------------------------
class FakeMonarch:
    def __init__(self, **payloads):
        self.payloads = payloads

    async def get_accounts(self):
        return self.payloads.get("accounts", {})

    async def get_savings_goals(self):
        return self.payloads.get("goals", {})

    async def get_cashflow_summary(self, start_date=None, end_date=None):
        return self.payloads.get("cashflow", {})

    async def get_budgets(self, start_date=None, end_date=None):
        return self.payloads.get("budget", {})

    async def get_recurring_transaction_streams(self, include_liabilities=True):
        return self.payloads.get("streams", {})


def source_with(**payloads):
    source = MonarchSource()
    source.mm = FakeMonarch(**payloads)
    return source


def run(coro):
    import asyncio

    return asyncio.run(coro)


def test_net_worth():
    source = source_with(accounts={"accounts": [
        {"currentBalance": 1000.0},
        {"currentBalance": 500.0, "isHidden": True},
        {"currentBalance": 2000.0, "includeInNetWorth": False},
        {"currentBalance": -250.0},
    ]})
    got = run(source._net_worth())
    expect(got == {"value": 750.0, "accounts": 2}, f"got {got}")

    missing = run(source_with(accounts={"accounts": []})._net_worth())
    expect(missing["value"] is None, f"empty accounts should be unknown, got {missing}")

    renamed = run(source_with(accounts={"nodes": [{"currentBalance": 5}]})._net_worth())
    expect(renamed["value"] is None, f"schema drift should be unknown, got {renamed}")


def test_cashflow():
    nested = {"summary": [{"summary": {"sumIncome": 100.0, "sumExpense": -40.0,
                                       "savings": 60.0, "savingsRate": 0.6}}]}
    got = run(source_with(cashflow=nested)._cashflow())
    expect(got["expense"] == 40.0, f"expense should be positive for display, got {got}")
    expect(got["savings"] == 60.0, f"got {got}")

    flat = run(source_with(cashflow={"summary": {"sumIncome": 10, "sumExpense": -4}})._cashflow())
    expect(flat["savings"] == 6.0, f"derived savings wrong: {flat}")

    for payload in ({}, {"summary": None}, {"summary": [None]}, None):
        got = run(source_with(cashflow=payload)._cashflow())
        expect(got["savings"] is None, f"{payload!r} should be unknown, got {got}")


def test_budget():
    rows = [
        {"category": {"id": "c1"}, "monthlyAmounts": [
            {"month": "1999-01-01", "plannedCashFlowAmount": 100.0, "actualAmount": 50.0},
            {"month": _month_start(), "plannedCashFlowAmount": 100.0, "actualAmount": 50.0}]},
        {"category": {"id": "c2"}, "monthlyAmounts": [
            {"month": _month_start(), "plannedCashFlowAmount": 0.0, "actualAmount": 27_000.0}]},
        {"category": {"id": "c3"}, "monthlyAmounts": [
            {"month": _month_start(), "plannedCashFlowAmount": 50.0, "actualAmount": -20.0}]},
    ]
    payload = {
        "budgetData": {"monthlyAmountsByCategory": rows},
        "categoryGroups": [{"categories": [{"id": "c1", "name": "Groceries"},
                                           {"id": "c2", "name": "Transfer"},
                                           {"id": "c3", "name": "Refunds"}]}],
    }
    got = run(source_with(budget=payload)._budget())
    expect(got["planned"] == 150.0, f"unbudgeted rows must not count: {got}")
    expect(got["actual"] == 50.0, f"refund/transfer handling wrong: {got}")
    expect(abs(got["pct"] - (50 / 150 * 100)) < 0.001, f"pct wrong: {got}")
    expect(got["month"], "month label missing")

    config.BUDGET_CATEGORY = "groceries"
    try:
        picked = run(source_with(budget=payload)._budget())
        expect(picked["name"] == "Groceries", f"category match failed: {picked}")
        expect(picked["planned"] == 100.0, f"got {picked}")
    finally:
        config.BUDGET_CATEGORY = ""


def test_next_bill():
    def stream(name, amount, when, **extra):
        record = {"stream": {"name": name, "amount": amount, "recurringType": "expense",
                             "isActive": True, **extra},
                  "nextForecastedTransaction": {"date": when, "amount": amount}}
        return record

    today = _today()
    payload = {"recurringTransactionStreams": [
        stream("Past", -10.0, "1999-01-01"),
        stream("Income", 500.0, today, recurringType="income"),
        stream("Zero", 0.0, today),
        stream("Small", -1.0, today),
        stream("Large", -900.0, today),
        stream("Later", -50.0, "2999-01-01"),
    ]}
    got = run(source_with(streams=payload)._next_bill())
    expect(got.get("name") == "Large",
           f"should pick the largest bill due today, got {got}")
    expect(got["amount"] == 900.0, f"amounts should be positive, got {got}")

    none = run(source_with(streams={"recurringTransactionStreams": []})._next_bill())
    expect(none.get("name") is None, f"empty stream list should be empty result: {none}")


def _today():
    from datetime import date

    return date.today().isoformat()


def _month_start():
    from datetime import date

    return date.today().replace(day=1).isoformat()


def test_auth_error_detection():
    expect(_looks_like_auth_error(RuntimeError("401 Unauthorized")), "401 not detected")
    expect(_looks_like_auth_error(RuntimeError("session expired")), "session not detected")
    expect(not _looks_like_auth_error(TimeoutError("timed out")), "timeout misread as auth")


# --- cache ----------------------------------------------------------------
def test_cache():
    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        return calls["n"]

    source = MonarchSource()
    original = config.CACHE_TTL
    try:
        config.CACHE_TTL = 3600
        first = run(source._cached("k", factory))
        second = run(source._cached("k", factory))
        expect(first == second == 1, f"cache miss: {first}, {second}")
        expect(calls["n"] == 1, f"factory called {calls['n']} times")

        # expire it
        stamp, value = source._cache["k"]
        source._cache["k"] = (stamp - config.CACHE_TTL - 1, value)
        run(source._cached("k", factory))
        expect(calls["n"] == 2, "expired entry was not refetched")

        config.CACHE_TTL = 0
        calls["n"] = 0
        run(source._cached("k", factory))
        run(source._cached("k", factory))
        expect(calls["n"] == 2, "CACHE_TTL=0 should always refetch")
    finally:
        config.CACHE_TTL = original


# --- push and notify ------------------------------------------------------
def test_push_client():
    seen = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            self.rfile.read(length)
            seen["path"] = self.path
            seen["auth"] = self.headers.get("Authorization")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"WebP received.")

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 18030), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = push_client.push_image(b"RIFFfake", "monarch")
    finally:
        server.shutdown()
        server.server_close()
    expect(result.get("body") == "WebP received.", f"reply not handled: {result}")
    expect(seen["path"].startswith("/v0/devices/pixel%20node%2F1/push"),
           f"device id not URL-encoded: {seen['path']}")
    expect(seen["auth"] == "Bearer dev-key", f"bad auth header: {seen['auth']}")


def test_notify_never_raises():
    expect(notify.send("x", "y") is False, "disabled notify should return False")
    original = config.GOTIFY_URL
    try:
        config.GOTIFY_URL = "not-a-url"
        expect(notify.send("x", "y") is False, "bad URL should return False, not raise")
    finally:
        config.GOTIFY_URL = original


# --- config validation ----------------------------------------------------
def _import_config(env):
    base = {
        "MONARCH_EMAIL": "a@b.invalid", "MONARCH_PASSWORD": "x",
        "TIDBYT_DEVICE_ID": "d", "TIDBYT_API_KEY": "k",
        "DATA_DIR": "/tmp/selftest-data",
    }
    base.update(env)
    code = "import app.config"
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        env={**os.environ, **base},
    )
    return proc.returncode, proc.stderr


def test_config_validation():
    cases = [
        ({"VIEWS": "nope"}, True),
        ({"UPDATE_INTERVAL": "0"}, True),
        ({"UPDATE_INTERVAL": "abc"}, True),
        ({"CACHE_TTL": "-1"}, True),
        ({"ALERT_AFTER_FAILURES": "0"}, True),
        ({"GOTIFY_URL": "gotify.local:8070"}, True),
        ({"TIDBYT_API_BASE": "192.168.1.9:8010/v0"}, True),
        ({"MONARCH_MFA_SECRET": "otpauth://totp/x?secret="}, True),
        ({"MONARCH_MFA_SECRET": "not base32!"}, True),
        ({"MONARCH_MFA_SECRET": "JBSWY3DPEHPK3PXP"}, False),
        ({"MONARCH_MFA_SECRET": "otpauth://totp/M:x?secret=JBSWY3DPEHPK3PXP&issuer=M"}, False),
    ]
    for env, should_fail in cases:
        code, stderr = _import_config(env)
        if should_fail:
            expect(code != 0, f"{env} should be rejected")
        else:
            expect(code == 0, f"{env} should be accepted: {stderr[-300:]}")


def main() -> int:
    check("money", test_money)
    check("compact_money", test_compact_money)
    check("dashboard_fit", test_dashboard_fit)
    check("dashboard_edges", test_dashboard_edges)
    check("dashboard_colors", test_dashboard_colors)
    check("error_frame", test_error_frame)
    check("alert_schedule", test_alert_schedule)
    check("safe_detail", test_safe_detail)
    check("net_worth", test_net_worth)
    check("cashflow", test_cashflow)
    check("budget", test_budget)
    check("next_bill", test_next_bill)
    check("auth_error_detection", test_auth_error_detection)
    check("cache", test_cache)
    check("push_client", test_push_client)
    check("notify_never_raises", test_notify_never_raises)
    check("config_validation", test_config_validation)

    if FAILURES:
        print(f"{len(FAILURES)} failure(s):")
        for failure in FAILURES:
            print("  FAIL", failure)
        return 1
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
