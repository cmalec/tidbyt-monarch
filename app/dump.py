"""Print the real shape of each Monarch payload.

Run this once after the first successful login, before trusting the parsers:
    docker run --rm -e ... image python -m app.dump
"""
import asyncio
import json

from app.monarch_client import MonarchSource


def sample(payload, depth=2):
    """Shrink a payload to keys and one example record per list."""
    def trim(obj, level):
        if level <= 0:
            return type(obj).__name__
        if isinstance(obj, dict):
            return {k: trim(v, level - 1) for k, v in list(obj.items())[:12]}
        if isinstance(obj, list):
            return [trim(obj[0], level - 1)] if obj else []
        return obj
    return trim(payload, depth)


async def main():
    source = MonarchSource()
    print("session:", await source.connect())

    checks = [
        ("accounts", source.mm.get_accounts()),
        ("budgets", source.mm.get_budgets()),
        ("savings_goals", source.mm.get_savings_goals()),
        ("cashflow_summary", source.mm.get_cashflow_summary()),
        ("recurring_streams", source.mm.get_recurring_transaction_streams(include_liabilities=True)),
    ]
    for name, coro in checks:
        try:
            payload = await coro
            print(f"\n=== {name}")
            print(json.dumps(sample(payload), indent=2, default=str)[:2500])
        except Exception as exc:
            print(f"\n=== {name} FAILED: {type(exc).__name__}: {exc}")

    print("\n=== parsed")
    for label, coro in [
        ("net_worth", source.net_worth()),
        ("budget", source.budget()),
        ("goal", source.goal()),
        ("cashflow", source.cashflow()),
        ("next_bill", source.next_bill()),
    ]:
        try:
            print(f"  {label}: {await coro}")
        except Exception as exc:
            print(f"  {label} FAILED: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
