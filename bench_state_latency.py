#!/usr/bin/env python3
"""
Benchmark state read/write latency.
Target: <10ms for both read and write operations.
"""

import asyncio
import time
from datetime import datetime
from lgdl.runtime.state import StateManager, Turn
from lgdl.runtime.storage.sqlite import SQLiteStateStorage


async def bench_state_latency():
    # Initialize state manager
    storage = SQLiteStateStorage()
    state_mgr = StateManager(persistent_storage=storage, ephemeral_ttl=300)

    conv_id = f"bench-{int(time.time() * 1000)}"

    # Benchmark: Get or create (write + read)
    t0 = time.perf_counter()
    state = await state_mgr.get_or_create(conv_id)
    create_latency = (time.perf_counter() - t0) * 1000

    # Benchmark: Update (write)
    turn = Turn(
        turn_num=1,
        timestamp=datetime.utcnow(),
        user_input="test input",
        sanitized_input="test input",
        matched_move="test_move",
        confidence=0.95,
        response="test response",
        extracted_params={"param1": "value1"}
    )

    t0 = time.perf_counter()
    await state_mgr.update(conv_id, turn, extracted_params={"param1": "value1"})
    write_latency = (time.perf_counter() - t0) * 1000

    # Benchmark: Read from cache (should be fast)
    t0 = time.perf_counter()
    state = await state_mgr.get_or_create(conv_id)
    cache_read_latency = (time.perf_counter() - t0) * 1000

    # Benchmark: Read from database (cold read) - use new StateManager instance
    state_mgr2 = StateManager(persistent_storage=storage, ephemeral_ttl=300)
    t0 = time.perf_counter()
    state = await state_mgr2.get_or_create(conv_id)
    db_read_latency = (time.perf_counter() - t0) * 1000

    print("=" * 60)
    print("State Management Latency Benchmark")
    print("=" * 60)
    print(f"Create conversation:        {create_latency:>6.2f}ms")
    print(f"Write turn:                 {write_latency:>6.2f}ms")
    print(f"Read from cache:            {cache_read_latency:>6.2f}ms")
    print(f"Read from database (cold):  {db_read_latency:>6.2f}ms")
    print("=" * 60)

    # Check if all operations meet <10ms target
    all_fast = (create_latency < 10 and write_latency < 10 and
                cache_read_latency < 10 and db_read_latency < 10)

    if all_fast:
        print("✅ ALL operations < 10ms - Target achieved!")
    else:
        print("⚠️  Some operations exceed 10ms target")
        if create_latency >= 10:
            print(f"   - Create: {create_latency:.2f}ms")
        if write_latency >= 10:
            print(f"   - Write: {write_latency:.2f}ms")
        if cache_read_latency >= 10:
            print(f"   - Cache read: {cache_read_latency:.2f}ms")
        if db_read_latency >= 10:
            print(f"   - DB read: {db_read_latency:.2f}ms")

    return all_fast


if __name__ == "__main__":
    result = asyncio.run(bench_state_latency())
    exit(0 if result else 1)
