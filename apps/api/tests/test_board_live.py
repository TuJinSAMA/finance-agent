#!/usr/bin/env python3
"""Test public board with rate limiting."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.services.public_board import get_public_market_board


async def test():
    print("Testing public market board with rate limiting...")
    print("This will take ~10-15 seconds due to controlled requests...")
    print()

    response = await get_public_market_board()

    print(f"Source: {response.source}")
    print(f"As of: {response.as_of}")
    print(f"Market state: {response.market_state.label}")
    print()

    all_metrics = response.macro + response.assets + response.custom
    success_count = sum(1 for m in all_metrics if m.value is not None)

    print(f"Successfully fetched: {success_count}/{len(all_metrics)} metrics")

    for metric in all_metrics:
        status = "✓" if metric.value is not None else "✗"
        print(f"  {status} {metric.name}: {metric.display}")

    if success_count > 0:
        print(f"\n✓ SUCCESS! Rate limiting is working!")
        return 0
    else:
        print(f"\n✗ All requests failed - may need to wait longer between requests")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(test()))
