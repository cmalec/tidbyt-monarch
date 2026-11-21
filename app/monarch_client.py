"""Monarch Money data access for the display app.

Uses monarchmoneycommunity. Field shapes are defensive: Monarch's GraphQL
schema moves, so every accessor tolerates missing keys and returns None
rather than raising, and `python -m app.dump` prints the real shapes.
"""
import os
import time
from datetime import date, datetime, timedelta, timezone

from monarchmoney import MonarchMoney, RequireMFAException

from app import config


def _num(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _find(obj, *keys):
    """Return the first present key's value, searching nested dicts/lists."""
    if isinstance(obj, dict):
        for key in keys:
            if key in obj and obj[key] is not None:
                return obj[key]
        for value in obj.values():
            found = _find(value, *keys)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find(item, *keys)
            if found is not None:
                return found
    return None


def _as_records(payload, *keys):
    """Pull a list of records out of a GraphQL payload."""
    for key in keys:
        value = payload.get(key) if isinstance(payload, dict) else None
        if isinstance(value, list):
            return value
    found = _find(payload, *keys)
    return found if isinstance(found, list) else []


class MonarchSource:
    """Thin, failure-tolerant wrapper over the Monarch API."""

    def __init__(self):
        self.mm = MonarchMoney(session_file=config.MONARCH_SESSION_FILE)
        self._cache: dict[str, tuple[float, object]] = {}

    async def _cached(self, key: str, factory):
        """Reuse a fetched payload until CACHE_TTL expires.

        Monarch's numbers change far slower than the panel refreshes, and each
        call is a request against a rate-limited private API.
        """
        if config.CACHE_TTL <= 0:
            return await factory()
        hit = self._cache.get(key)
        now = time.monotonic()
        if hit is not None and now - hit[0] < config.CACHE_TTL:
            return hit[1]
        value = await factory()
        self._cache[key] = (now, value)
        return value

    async def connect(self) -> str:
        """Reuse a saved session when possible, else log in. Returns how."""
        if os.path.exists(config.MONARCH_SESSION_FILE):
            try:
                self.mm.load_session(config.MONARCH_SESSION_FILE)
                await self.mm.get_accounts()
                return "saved session"
            except Exception:
                pass  # expired or corrupt, fall through to a fresh login

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
            )
        os.makedirs(os.path.dirname(config.MONARCH_SESSION_FILE) or ".", exist_ok=True)
        return "fresh login"

    # --- data -----------------------------------------------------------
    async def net_worth(self) -> dict:
        return await self._cached("networth", self._net_worth)

    async def _net_worth(self) -> dict:
        payload = await self.mm.get_accounts()
        accounts = _as_records(payload, "accounts")
        total = 0.0
        counted = 0
        for acct in accounts:
            if acct.get("deletedAt") or acct.get("isHidden"):
                continue
            if acct.get("includeInNetWorth") is False:
                continue
            balance = _num(acct.get("currentBalance"))
            if balance is None:
                continue
            total += balance
            counted += 1
        return {"value": total, "accounts": counted}

    async def goal(self) -> dict:
        return await self._cached("goal", self._goal)

    async def _goal(self) -> dict:
        payload = await self.mm.get_savings_goals()
        goals = _as_records(payload, "savingsGoals", "goals")
        active = [g for g in goals if not g.get("archivedAt") and g.get("status") != "archived"]
        chosen = None
        if config.GOAL_ID:
            chosen = next((g for g in active if str(g.get("id")) == config.GOAL_ID), None)
        if chosen is None and active:
            chosen = active[0]
        if chosen is None:
            return {"name": None}

        name = chosen.get("name") or "Goal"
        target = _num(_find(chosen, "targetAmount", "target", "amount"))
        current = _num(_find(chosen, "currentAmount", "currentBalance", "balance", "savedAmount"), 0.0)
        pct = None
        if target and target > 0:
            pct = max(0.0, min(100.0, current / target * 100.0))
        return {"name": name, "target": target, "current": current, "pct": pct}

    async def cashflow(self) -> dict:
        return await self._cached("cashflow", self._cashflow)

    async def _cashflow(self) -> dict:
        today = date.today()
        start = today.replace(day=1)
        payload = await self.mm.get_cashflow_summary(
            start_date=start.isoformat(), end_date=today.isoformat()
        )
        summary = (payload.get("summary") or [{}])[0].get("summary", {}) if isinstance(
            payload.get("summary"), list) else payload.get("summary", {})

        income = _num(summary.get("sumIncome"))
        # Monarch reports expenses as a negative number
        expense = _num(summary.get("sumExpense"))
        expense = abs(expense) if expense is not None else None
        savings = _num(summary.get("savings"))
        if savings is None and income is not None and expense is not None:
            savings = income - expense
        rate = _num(summary.get("savingsRate"))
        return {
            "income": income,
            "expense": expense,
            "savings": savings,
            "rate": rate,
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

        names = {}

        def collect(node):
            if isinstance(node, dict):
                ident, name = node.get("id"), node.get("name")
                if ident and isinstance(name, str) and name:
                    names[str(ident)] = name
                for value in node.values():
                    collect(value)
            elif isinstance(node, list):
                for value in node:
                    collect(value)

        collect(payload.get("categoryGroups"))

        rows = (payload.get("budgetData") or {}).get("monthlyAmountsByCategory") or []
        total_planned = total_actual = 0.0
        chosen = None
        for row in rows:
            category = row.get("category") or {}
            amounts = row.get("monthlyAmounts") or []
            if not amounts:
                continue
            month = amounts[0]
            planned = _num(month.get("plannedCashFlowAmount"), 0.0) or 0.0
            actual = abs(_num(month.get("actualAmount"), 0.0) or 0.0)
            name = names.get(str(category.get("id")), "")
            if config.BUDGET_CATEGORY and name.lower() == config.BUDGET_CATEGORY.lower():
                chosen = {"name": name, "planned": planned, "actual": actual}
            # Totals only cover categories that actually have a budget set.
            # Unbudgeted rows include transfers, credit card payments and
            # income, and summing them produced 449% "used" on real data.
            if planned > 0:
                total_planned += planned
                total_actual += actual

        if config.BUDGET_CATEGORY:
            if not chosen:
                return {"name": None, "missing": config.BUDGET_CATEGORY}
            target = chosen
        else:
            target = {"name": "TOTAL", "planned": total_planned, "actual": total_actual}

        pct = None
        if target["planned"] > 0:
            pct = target["actual"] / target["planned"] * 100.0
        return {**target, "pct": pct, "month": start.strftime("%b")}

    async def dashboard(self) -> dict:
        """Everything the 2x2 grid needs, in three API calls."""
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
        today = datetime.now(timezone.utc).date()
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
                continue
            try:
                when = date.fromisoformat(str(raw_date)[:10])
            except ValueError:
                continue
            if when < today:
                continue
            upcoming.append((when, abs(amount), stream.get("name") or "Bill"))
        if not upcoming:
            return {"name": None}
        when, amount, name = min(upcoming)
        return {"name": name, "amount": amount, "days": (when - today).days}
