"""Monarch Money data access for the display app.

Uses monarchmoneycommunity. Field shapes are defensive: Monarch's GraphQL
schema moves, so every accessor tolerates missing keys and returns None
rather than raising, and `python -m app.dump` prints the real shapes.
"""
import os
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
        today = date.today()
        start = today.replace(day=1)
        payload = await self.mm.get_cashflow_summary(
            start_date=start.isoformat(), end_date=today.isoformat()
        )
        income = _num(_find(payload, "sumIncome", "totalIncome", "income"))
        expense = _num(_find(payload, "sumExpense", "totalExpense", "expense"))
        savings = _num(_find(payload, "savings", "netSavings", "net"))
        if savings is None and income is not None and expense is not None:
            savings = income - expense
        return {"income": income, "expense": expense, "savings": savings, "month": start.strftime("%b")}

    async def next_bill(self) -> dict:
        payload = await self.mm.get_recurring_transaction_streams(include_liabilities=True)
        streams = _as_records(payload, "recurringTransactionStreams", "streams")
        today = datetime.now(timezone.utc).date()
        upcoming = []
        for stream in streams:
            if stream.get("isActive") is False:
                continue
            amount = _num(_find(stream, "amount", "averageAmount"))
            if amount is None or amount >= 0:
                continue  # bills only: outgoing money
            raw = _find(stream, "nextDate", "nextForecast", "nextOccurrence")
            if not raw:
                continue
            try:
                when = datetime.fromisoformat(str(raw).replace("Z", "+00:00")).date()
            except ValueError:
                try:
                    when = date.fromisoformat(str(raw)[:10])
                except ValueError:
                    continue
            if when < today - timedelta(days=1):
                continue
            upcoming.append((when, abs(amount), stream.get("name") or "Bill"))
        if not upcoming:
            return {"name": None}
        when, amount, name = min(upcoming)
        return {"name": name, "amount": amount, "days": (when - today).days}
