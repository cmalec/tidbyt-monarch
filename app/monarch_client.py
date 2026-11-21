"""Monarch Money data access for the display app.

Uses monarchmoneycommunity. Monarch's GraphQL schema moves, so every accessor
tolerates missing keys and returns None rather than raising. `None` is
meaningful: the renderer shows it as neutral "n/a" rather than inventing a
number. `python -m app.dump` prints the real payload shapes.
"""
import math
import os
import stat
import time
from datetime import date

from monarchmoney import MonarchMoney, RequireMFAException

from app import config

_AUTH_HINTS = ("authenticat", "unauthorized", "forbidden", "401", "403",
               "session", "token", "login", "credential")


def _num(value, default=None):
    """Float, or default. Rejects NaN/inf so they never reach the display."""
    if value is None:
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _as_records(payload, *keys):
    """Pull a list of records out of a GraphQL payload."""
    if not isinstance(payload, dict):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def _looks_like_auth_error(exc: Exception) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return any(hint in text for hint in _AUTH_HINTS)


class MonarchSource:
    """Thin, failure-tolerant wrapper over the Monarch API."""

    def __init__(self):
        self.mm = MonarchMoney(session_file=config.MONARCH_SESSION_FILE)
        self._cache: dict[str, tuple[float, object]] = {}
        self._primed_accounts = None

    async def _cached(self, key: str, factory):
        """Reuse a fetched payload until CACHE_TTL expires.

        Monarch's numbers change far slower than the panel refreshes, and each
        call is a request against a rate-limited private API.
        """
        if config.CACHE_TTL <= 0:
            return await factory()
        hit = self._cache.get(key)
        if hit is not None and time.monotonic() - hit[0] < config.CACHE_TTL:
            return hit[1]
        value = await factory()
        # timestamp after the fetch: a slow response should not eat the TTL
        self._cache[key] = (time.monotonic(), value)
        return value

    async def connect(self) -> str:
        """Reuse a saved session when possible, else log in. Returns how."""
        session_dir = os.path.dirname(config.MONARCH_SESSION_FILE) or "."
        os.makedirs(session_dir, mode=0o700, exist_ok=True)
        try:
            os.chmod(session_dir, 0o700)
        except OSError:
            pass
        # a fresh login writes the session file; make it private by default
        os.umask(0o077)

        if os.path.exists(config.MONARCH_SESSION_FILE):
            try:
                self.mm.load_session(config.MONARCH_SESSION_FILE)
                # load_session succeeds on a stale pickle, so prove it works
                self._primed_accounts = await self.mm.get_accounts()
                return "saved session"
            except Exception as exc:
                if not _looks_like_auth_error(exc):
                    # network blip or 5xx: do not burn a password login on it
                    raise
                self._primed_accounts = None

        try:
            await self.mm.login(
                config.MONARCH_EMAIL,
                config.MONARCH_PASSWORD,
                mfa_secret_key=config.MONARCH_MFA_SECRET or None,
                save_session=True,
            )
        except RequireMFAException:
            raise RuntimeError(
                "Monarch requires an MFA code and no usable MONARCH_MFA_SECRET is set. "
                "Set MONARCH_MFA_SECRET to the TOTP secret from Settings > Security."
            ) from None

        self._restrict_session_file()
        self._primed_accounts = None
        return "fresh login"

    def _restrict_session_file(self) -> None:
        try:
            os.chmod(config.MONARCH_SESSION_FILE, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass

    async def close(self) -> None:
        closer = getattr(self.mm, "close", None)
        if closer is None:
            return
        result = closer()
        if hasattr(result, "__await__"):
            await result

    # --- data -----------------------------------------------------------
    async def net_worth(self) -> dict:
        return await self._cached("networth", self._net_worth)

    async def _net_worth(self) -> dict:
        payload = self._primed_accounts
        self._primed_accounts = None
        if payload is None:
            payload = await self.mm.get_accounts()
        accounts = _as_records(payload, "accounts")

        total = 0.0
        counted = 0
        for acct in accounts:
            if not isinstance(acct, dict):
                continue
            if acct.get("deletedAt") or acct.get("isHidden"):
                continue
            if acct.get("includeInNetWorth") is False:
                continue
            balance = _num(acct.get("currentBalance"))
            if balance is None:
                continue
            total += balance
            counted += 1

        # No usable accounts means the payload changed shape, not that the
        # net worth is zero. Report "unknown" so the panel shows n/a.
        if counted == 0:
            return {"value": None, "accounts": 0}
        return {"value": total, "accounts": counted}

    async def goal(self) -> dict:
        return await self._cached("goal", self._goal)

    async def _goal(self) -> dict:
        payload = await self.mm.get_savings_goals()
        goals = _as_records(payload, "savingsGoals", "goals")
        active = [g for g in goals if isinstance(g, dict)
                  and not g.get("archivedAt") and g.get("status") != "archived"]
        chosen = None
        if config.GOAL_ID:
            chosen = next((g for g in active if str(g.get("id")) == config.GOAL_ID), None)
        if chosen is None and active:
            chosen = active[0]
        if chosen is None:
            return {"name": None}

        # Read only the goal's own fields. A recursive search could pick up a
        # linked account's balance and present it as goal progress.
        target = _num(chosen.get("targetAmount"))
        current = _num(chosen.get("currentAmount"), 0.0)
        pct = None
        if target and target > 0 and current is not None:
            pct = max(0.0, min(100.0, current / target * 100.0))
        return {
            "name": chosen.get("name") or "Goal",
            "target": target,
            "current": current,
            "pct": pct,
        }

    async def cashflow(self) -> dict:
        return await self._cached("cashflow", self._cashflow)

    async def _cashflow(self) -> dict:
        today = date.today()
        start = today.replace(day=1)
        payload = await self.mm.get_cashflow_summary(
            start_date=start.isoformat(), end_date=today.isoformat()
        )

        summary = {}
        if isinstance(payload, dict):
            raw = payload.get("summary")
            if isinstance(raw, list) and raw:
                first = raw[0]
                if isinstance(first, dict):
                    inner = first.get("summary")
                    summary = inner if isinstance(inner, dict) else first
            elif isinstance(raw, dict):
                summary = raw

        income = _num(summary.get("sumIncome"))
        expense = _num(summary.get("sumExpense"))
        if expense is not None:
            expense = abs(expense)  # Monarch reports expenses negative
        savings = _num(summary.get("savings"))
        if savings is None and income is not None and expense is not None:
            savings = income - expense
        return {
            "income": income,
            "expense": expense,
            "savings": savings,
            "rate": _num(summary.get("savingsRate")),
            "month": start.strftime("%b"),
        }

    async def budget(self) -> dict:
        return await self._cached("budget", self._budget)

    async def _budget(self) -> dict:
        """Budget progress for the current month.

        Shows one category when BUDGET_CATEGORY names one, else the totals.
        """
        today = date.today()
        start = today.replace(day=1)
        payload = await self.mm.get_budgets(
            start_date=start.isoformat(), end_date=today.isoformat()
        )
        if not isinstance(payload, dict):
            return {"name": None, "missing": None, "pct": None}

        # Category names live on the category records, not on the budget rows.
        names = {}
        for group in _as_records(payload, "categoryGroups"):
            if not isinstance(group, dict):
                continue
            for category in _as_records(group, "categories"):
                if isinstance(category, dict) and category.get("name"):
                    names[str(category.get("id"))] = category["name"]

        rows = ((payload.get("budgetData") or {}).get("monthlyAmountsByCategory") or [])
        wanted_month = start.isoformat()
        total_planned = total_actual = 0.0
        chosen = None
        for row in rows:
            if not isinstance(row, dict):
                continue
            category = row.get("category") or {}
            amounts = row.get("monthlyAmounts") or []
            if not amounts:
                continue
            month = next(
                (m for m in amounts if isinstance(m, dict) and m.get("month") == wanted_month),
                amounts[0],
            )
            if not isinstance(month, dict):
                continue
            planned = _num(month.get("plannedCashFlowAmount"), 0.0) or 0.0
            actual_raw = _num(month.get("actualAmount"), 0.0) or 0.0
            # Expenses record positive spend; a refund can make it negative and
            # should reduce usage rather than inflate it.
            actual = actual_raw if actual_raw > 0 else 0.0
            name = names.get(str(category.get("id")), "")
            if config.BUDGET_CATEGORY and name and name.lower() == config.BUDGET_CATEGORY.lower():
                chosen = {"name": name, "planned": planned, "actual": actual}
            # Totals only cover categories that actually have a budget set.
            # Unbudgeted rows include transfers, credit card payments and
            # income, and summing them produced 449% "used" on real data.
            if planned > 0:
                total_planned += planned
                total_actual += actual

        if config.BUDGET_CATEGORY:
            if not chosen:
                return {"name": None, "missing": config.BUDGET_CATEGORY, "pct": None}
            target = chosen
        else:
            target = {"name": "TOTAL", "planned": total_planned, "actual": total_actual}

        pct = None
        if target["planned"] > 0:
            pct = target["actual"] / target["planned"] * 100.0
        return {**target, "pct": pct, "month": start.strftime("%b")}

    async def dashboard(self) -> dict:
        """Everything the 2x2 grid needs, in three API calls (cached)."""
        return {
            "networth": await self.net_worth(),
            "budget": await self.budget(),
            "cashflow": await self.cashflow(),
        }

    async def next_bill(self) -> dict:
        return await self._cached("bill", self._next_bill)

    async def _next_bill(self) -> dict:
        payload = await self.mm.get_recurring_transaction_streams(include_liabilities=True)
        streams = _as_records(payload, "recurringTransactionStreams", "streams")
        today = date.today()
        upcoming = []
        for entry in streams:
            # Records nest the definition under "stream" and the due date under
            # "nextForecastedTransaction".
            stream = entry.get("stream") if isinstance(entry, dict) else None
            if not isinstance(stream, dict):
                continue
            if stream.get("isActive") is False:
                continue
            if (stream.get("recurringType") or "").lower() == "income":
                continue
            forecast = entry.get("nextForecastedTransaction") or {}
            raw_date = forecast.get("date") or stream.get("baseDate")
            amount = _num(forecast.get("amount"), _num(stream.get("amount")))
            if not raw_date or amount is None or amount >= 0:
                continue  # bills only, and a zero amount is not a bill
            try:
                when = date.fromisoformat(str(raw_date)[:10])
            except ValueError:
                continue
            if when < today:
                continue
            upcoming.append((when, -abs(amount), stream.get("name") or "Bill"))
        if not upcoming:
            return {"name": None}
        # soonest first; on a tie prefer the larger bill
        when, negative_amount, name = min(upcoming)
        return {"name": name, "amount": -negative_amount, "days": (when - today).days}
