"""Prove the cache works: second dashboard frame must be near-instant, and
CACHE_TTL=0 must disable it."""
import asyncio
import time

from app import config
from app.monarch_client import MonarchSource


async def main():
    src = MonarchSource()
    await src.connect()
    print(f"CACHE_TTL={config.CACHE_TTL}s")

    t0 = time.perf_counter()
    first = await src.dashboard()
    t1 = time.perf_counter()
    second = await src.dashboard()
    t2 = time.perf_counter()

    cold = t1 - t0
    warm = t2 - t1
    print(f"first dashboard:  {cold:.2f}s")
    print(f"second dashboard: {warm:.3f}s")
    print(f"identical data:   {first == second}")
    print(f"cache keys held:  {sorted(src._cache)}")

    if config.CACHE_TTL > 0:
        assert first == second, "cached data differs from fresh data"
        assert warm < max(0.2, cold * 0.5), f"cache not effective: {warm:.3f}s vs {cold:.2f}s"
        # expiry: pretend the entry is old
        for key, (stamp, value) in list(src._cache.items()):
            src._cache[key] = (stamp - config.CACHE_TTL - 1, value)
        t3 = time.perf_counter()
        await src.dashboard()
        t4 = time.perf_counter()
        print(f"after expiry:     {t4 - t3:.2f}s (should be near the cold time)")
        assert (t4 - t3) > warm, "expired entries were served from cache"
        print("cache ok")
    else:
        assert warm > 0.05, "CACHE_TTL=0 should re-fetch"
        print("cache disabled as configured")


if __name__ == "__main__":
    asyncio.run(main())
