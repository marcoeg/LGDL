# LGDL v1.0 Production Hardening Plan

**Status**: Planning phase (2025-10-31)
**Prerequisites**: v1.0-RC complete (slot-filling, state management, 218 tests passing)
**Duration**: 8-10 weeks
**Effort**: ~2,600 lines of code, ~60 tests
**Goal**: Production-ready LGDL runtime with 99.9% uptime, <500ms P95 latency

---

## Executive Summary

Transform v1.0-RC (feature-complete) into production-ready v1.0 with enterprise-grade reliability, scalability, and observability.

### Current State (v1.0-RC)
✅ **Core Features Complete**:
- Template security with AST validation
- Multi-game API with registry
- Deterministic embeddings
- Multi-turn state management with SQLite
- Context enrichment
- Declarative slot-filling
- 218 tests passing (100% backward compatible)

⚠️ **Production Gaps**:
- SQLite only (not suitable for high-scale production)
- No connection pooling or caching optimization
- No rate limiting or circuit breakers
- Minimal monitoring and metrics
- No load testing validation
- Basic security (no encryption, PII handling)
- Limited deployment tooling

### Target State (v1.0 Production)
✅ **Production-Ready Runtime**:
- Redis + PostgreSQL storage backends
- <500ms P95 latency at 100+ concurrent conversations
- Rate limiting and circuit breakers
- Comprehensive monitoring (Prometheus, Grafana)
- Load tested to 5x capacity
- PII redaction and GDPR compliance
- 1-click Docker/K8s deployment
- Production runbooks and troubleshooting guides

---

## Phase 1: Production Storage Backends

**Duration**: 2 weeks (Days 1-10)
**Effort**: ~300 lines of code, 20 tests
**Priority**: High (blocks scaling)

### Overview
Replace or complement SQLite with production-grade storage:
- **Redis**: High-throughput ephemeral state (cache, TTL-based)
- **PostgreSQL**: Durable persistent state (conversation history, slots)
- **Migration**: Tools to migrate from SQLite → PostgreSQL/Redis

### Task 1.1: Redis Backend Implementation

**File**: `lgdl/runtime/storage/redis.py` (new, ~150 lines)

**Class**: `RedisStateStorage` implementing `StorageBackend` protocol

**Key Methods**:
```python
class RedisStateStorage(StorageBackend):
    def __init__(self, redis_url: str, ttl: int = 3600):
        """
        Redis storage for ephemeral conversation state.

        Args:
            redis_url: redis://localhost:6379/0
            ttl: Default TTL for conversations in seconds
        """

    async def create_conversation(conversation_id: str) -> PersistentState
    async def load_conversation(conversation_id: str) -> Optional[PersistentState]
    async def save_conversation(state: PersistentState) -> None

    # Slot storage (same interface as SQLite)
    async def save_slot(conversation_id, move_id, slot_name, value, type)
    async def get_slot(conversation_id, move_id, slot_name) -> Any
    async def get_all_slots_for_move(conversation_id, move_id) -> Dict
    async def clear_slots_for_move(conversation_id, move_id)
```

**Data Structures**:
```
# Conversation metadata
conversation:{id}:meta → JSON {created_at, updated_at, current_move_state, ...}

# Turns (list)
conversation:{id}:turns → LIST of JSON turns

# Slots (hash)
conversation:{id}:move:{move_id}:slots → HASH {slot_name: value}

# Extracted context (hash)
conversation:{id}:context → HASH {key: value}

# TTL applied to all keys
EXPIRE conversation:{id}:* 3600
```

**Features**:
- Atomic operations with Lua scripts
- Pipelining for batch operations
- Connection pooling (redis-py pool)
- Automatic expiry (TTL-based cleanup)
- Pub/Sub for real-time events (optional)

**Configuration**:
```python
LGDL_REDIS_URL=redis://localhost:6379/0
LGDL_REDIS_TTL=3600
LGDL_REDIS_POOL_SIZE=10
LGDL_REDIS_POOL_TIMEOUT=5
```

**Tests** (`tests/test_redis_storage.py`):
- test_create_and_load_conversation
- test_save_and_retrieve_turns
- test_slot_persistence
- test_ttl_expiry
- test_connection_pooling
- test_atomic_operations
- test_cleanup_old_conversations
- test_concurrent_access
- test_error_handling
- test_failover

**Dependencies**: `redis[asyncio]>=5.0.0`

---

### Task 1.2: PostgreSQL Backend Implementation

**File**: `lgdl/runtime/storage/postgres.py` (new, ~150 lines)

**Class**: `PostgresStateStorage` implementing `StorageBackend` protocol

**Schema**:
```sql
CREATE TABLE conversations (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    current_move_state TEXT,
    awaiting_response BOOLEAN DEFAULT FALSE,
    last_question TEXT,
    awaiting_slot_for_move TEXT,
    awaiting_slot_name TEXT,
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE turns (
    id BIGSERIAL PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    turn_num INTEGER NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    user_input TEXT NOT NULL,
    sanitized_input TEXT NOT NULL,
    matched_move TEXT,
    confidence REAL NOT NULL,
    response TEXT NOT NULL,
    extracted_params JSONB DEFAULT '{}'::jsonb,
    metadata JSONB DEFAULT '{}'::jsonb,
    UNIQUE(conversation_id, turn_num)
);

CREATE TABLE extracted_context (
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    value JSONB NOT NULL,
    PRIMARY KEY (conversation_id, key)
);

CREATE TABLE slots (
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    move_id TEXT NOT NULL,
    slot_name TEXT NOT NULL,
    slot_value JSONB NOT NULL,
    slot_type TEXT,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (conversation_id, move_id, slot_name)
);

-- Indexes
CREATE INDEX idx_turns_conversation_num ON turns(conversation_id, turn_num);
CREATE INDEX idx_conversations_updated ON conversations(updated_at);
CREATE INDEX idx_slots_conversation_move ON slots(conversation_id, move_id);

-- GIN indexes for JSONB
CREATE INDEX idx_turns_params_gin ON turns USING GIN (extracted_params);
CREATE INDEX idx_context_value_gin ON extracted_context USING GIN (value);
```

**Features**:
- JSONB for efficient JSON querying
- Connection pooling with asyncpg
- Prepared statements
- Partitioning by date (for high-volume)
- Read replicas support (async replication)
- VACUUM automation

**Configuration**:
```python
LGDL_POSTGRES_URL=postgresql://user:pass@localhost:5432/lgdl
LGDL_POSTGRES_POOL_MIN=5
LGDL_POSTGRES_POOL_MAX=20
LGDL_POSTGRES_TIMEOUT=10
LGDL_POSTGRES_COMMAND_TIMEOUT=5
```

**Tests** (`tests/test_postgres_storage.py`):
- test_create_and_load_conversation
- test_jsonb_query_performance
- test_slot_persistence
- test_concurrent_transactions
- test_connection_pooling
- test_cleanup_with_cascade
- test_large_conversation_history
- test_batch_operations
- test_read_replica (if configured)
- test_failover

**Dependencies**: `asyncpg>=0.29.0`

---

### Task 1.3: Storage Migration Tooling

**File**: `lgdl/cli/migrate.py` (new, ~100 lines)

**Commands**:
```bash
# Migrate from SQLite to PostgreSQL
lgdl migrate sqlite-to-postgres \
  --source ~/.lgdl/conversations.db \
  --target postgresql://localhost/lgdl \
  --batch-size 100 \
  --dry-run

# Verify migration
lgdl migrate verify \
  --source ~/.lgdl/conversations.db \
  --target postgresql://localhost/lgdl

# Export/import for backup
lgdl export --source postgresql://localhost/lgdl --output backup.jsonl
lgdl import --target postgresql://localhost/lgdl --input backup.jsonl
```

**Features**:
- Batch migration with progress bar
- Dry-run mode (validation only)
- Data integrity verification (counts, checksums)
- Resume on failure
- Parallel migration for large datasets

**Implementation**:
```python
class StorageMigrator:
    async def migrate(
        source: StorageBackend,
        target: StorageBackend,
        batch_size: int = 100,
        dry_run: bool = False
    ):
        # 1. Count source conversations
        # 2. Migrate in batches
        # 3. Verify each batch
        # 4. Report progress
        # 5. Final integrity check
```

**Tests** (`tests/test_migration.py`):
- test_sqlite_to_postgres_migration
- test_dry_run_no_changes
- test_data_integrity_verification
- test_resume_after_failure
- test_large_dataset_migration

---

### Task 1.4: Hybrid Storage Strategy

**File**: `lgdl/runtime/storage/hybrid.py` (new, ~50 lines)

**Pattern**: Redis (cache) + PostgreSQL (persistent)

**Implementation**:
```python
class HybridStateStorage(StorageBackend):
    def __init__(self, redis: RedisStateStorage, postgres: PostgresStateStorage):
        self.cache = redis  # Fast ephemeral
        self.persistent = postgres  # Durable

    async def load_conversation(conversation_id):
        # Try cache first
        state = await self.cache.load_conversation(conversation_id)
        if state:
            return state

        # Fallback to persistent
        state = await self.persistent.load_conversation(conversation_id)
        if state:
            # Warm cache
            await self.cache.save_conversation(state)
        return state

    async def save_conversation(state):
        # Write to both (cache + persistent)
        await asyncio.gather(
            self.cache.save_conversation(state),
            self.persistent.save_conversation(state)
        )
```

**Benefits**:
- Fast reads from Redis
- Durable writes to PostgreSQL
- Automatic cache warming
- Failover if cache unavailable

---

## Phase 2: Performance Optimization

**Duration**: 1 week (Days 11-15)
**Effort**: ~200 lines of code, 10 tests
**Priority**: High (performance SLA)

### Task 2.1: Pattern Cache Warming

**File**: `lgdl/runtime/matcher.py` (modify, +50 lines)

**Problem**: First match per pattern is slow (embedding computation)

**Solution**: Pre-compute on startup
```python
class TwoStageMatcher:
    async def warm_cache(self, compiled_game: dict):
        """Pre-compute embeddings for all patterns on startup"""
        for move in compiled_game["moves"]:
            for trigger in move["triggers"]:
                for pattern in trigger["patterns"]:
                    # Compute embedding
                    await self._get_embedding(pattern["text"])

        print(f"[Cache] Warmed {pattern_count} patterns")
```

**Metrics**: Track cache hit rate, cold start time

**Configuration**:
```python
LGDL_WARM_CACHE_ON_STARTUP=true
LGDL_CACHE_WARMING_TIMEOUT=30
```

**Tests**:
- test_cache_warming_on_startup
- test_cache_hit_rate_after_warming

---

### Task 2.2: Connection Pooling

**File**: `lgdl/runtime/storage/pooling.py` (new, ~80 lines)

**Implementation**:
```python
class ConnectionPool:
    """Generic connection pool for storage backends"""

    def __init__(
        self,
        min_size: int = 5,
        max_size: int = 20,
        timeout: float = 30.0,
        max_lifetime: float = 3600.0
    ):
        self.min_size = min_size
        self.max_size = max_size
        self.timeout = timeout

        # Pool management
        self._available = asyncio.Queue()
        self._in_use = set()

    async def acquire(self) -> Connection:
        """Get connection from pool (blocking if pool exhausted)"""

    async def release(self, conn: Connection):
        """Return connection to pool"""

    async def close_all(self):
        """Close all connections"""
```

**Features**:
- Minimum pool size (warm connections)
- Maximum pool size (prevent resource exhaustion)
- Connection health checks
- Automatic reconnection on failure
- Connection lifetime management
- Pool statistics

**Metrics**:
- Pool size (current)
- Connections in use
- Connections available
- Acquire wait time
- Connection errors

**Tests**:
- test_pool_min_size_maintained
- test_pool_max_size_enforced
- test_connection_reuse
- test_health_checks
- test_automatic_reconnection

---

### Task 2.3: Batch State Operations

**File**: `lgdl/runtime/state.py` (modify, +40 lines)

**Problem**: Multiple slot writes = multiple DB roundtrips

**Solution**: Batch operations
```python
class StateManager:
    async def batch_save_slots(
        self,
        conversation_id: str,
        move_id: str,
        slots: Dict[str, Any]
    ):
        """Save multiple slots in single transaction"""
        # Single BEGIN/COMMIT with multiple INSERTs

    async def batch_update_conversations(
        self,
        updates: List[Tuple[str, PersistentState]]
    ):
        """Update multiple conversations in one transaction"""
```

**Benefits**:
- Reduce slot write latency: 5ms × 3 slots = 15ms → 5ms total
- Reduce transaction overhead
- Improve throughput

**Tests**:
- test_batch_slot_writes
- test_batch_conversation_updates
- test_transaction_atomicity

---

### Task 2.4: Latency Monitoring

**File**: `lgdl/runtime/metrics.py` (new, ~30 lines)

**Implementation**:
```python
import time
from functools import wraps
from typing import Dict, List
import statistics

class LatencyTracker:
    """Track P50/P95/P99 latency for critical paths"""

    def __init__(self):
        self.measurements: Dict[str, List[float]] = {}

    def record(self, operation: str, duration_ms: float):
        if operation not in self.measurements:
            self.measurements[operation] = []
        self.measurements[operation].append(duration_ms)

    def get_percentiles(self, operation: str) -> Dict[str, float]:
        values = sorted(self.measurements.get(operation, []))
        if not values:
            return {}

        return {
            "p50": statistics.quantiles(values, n=2)[0],
            "p95": statistics.quantiles(values, n=20)[18],
            "p99": statistics.quantiles(values, n=100)[98],
            "count": len(values),
            "mean": statistics.mean(values)
        }

# Decorator for easy instrumentation
def track_latency(operation: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.perf_counter()
            result = await func(*args, **kwargs)
            duration_ms = (time.perf_counter() - start) * 1000
            latency_tracker.record(operation, duration_ms)
            return result
        return wrapper
    return decorator

# Usage
@track_latency("state_read")
async def load_conversation(conversation_id):
    ...
```

**Tracked Operations**:
- `state_read` - Load conversation
- `state_write` - Save conversation
- `slot_write` - Save slot
- `pattern_match` - Match user input
- `capability_call` - Execute capability
- `turn_total` - Full turn processing

**Alerts**:
- P95 > 500ms → Warning
- P99 > 1000ms → Critical
- Mean > 200ms → Investigation

**Tests**:
- test_latency_tracking
- test_percentile_calculation
- test_decorator_integration

---

## Phase 3: Production Safety

**Duration**: 1 week (Days 16-20)
**Effort**: ~300 lines of code, 15 tests
**Priority**: High (reliability)

### Task 3.1: Rate Limiting

**File**: `lgdl/runtime/rate_limiter.py` (new, ~100 lines)

**Algorithm**: Token bucket with Redis backend

**Implementation**:
```python
class RateLimiter:
    """Token bucket rate limiter with Redis backend"""

    def __init__(
        self,
        redis_client,
        user_limit: str = "10/minute",
        conversation_limit: str = "20/minute"
    ):
        self.redis = redis_client
        self.user_limit = self._parse_limit(user_limit)
        self.conv_limit = self._parse_limit(conversation_limit)

    async def check_user_limit(self, user_id: str) -> bool:
        """Check if user is within rate limit"""
        key = f"ratelimit:user:{user_id}"
        return await self._check_limit(key, self.user_limit)

    async def check_conversation_limit(self, conversation_id: str) -> bool:
        """Check if conversation is within rate limit"""
        key = f"ratelimit:conversation:{conversation_id}"
        return await self._check_limit(key, self.conv_limit)

    async def _check_limit(self, key: str, limit: Limit) -> bool:
        # Token bucket algorithm
        # Lua script for atomic increment + expiry
        lua_script = """
        local key = KEYS[1]
        local limit = tonumber(ARGV[1])
        local window = tonumber(ARGV[2])
        local current = redis.call('INCR', key)
        if current == 1 then
            redis.call('EXPIRE', key, window)
        end
        return current <= limit
        """
        return await self.redis.eval(lua_script, [key], [limit.count, limit.window_seconds])
```

**Integration**: Middleware in `lgdl/runtime/api.py`
```python
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # Check user rate limit
    user_id = request.headers.get("X-User-ID") or "anonymous"
    if not await rate_limiter.check_user_limit(user_id):
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded"},
            headers={"Retry-After": "60"}
        )

    # Check conversation rate limit (if present)
    conversation_id = await extract_conversation_id(request)
    if conversation_id and not await rate_limiter.check_conversation_limit(conversation_id):
        return JSONResponse(status_code=429, ...)

    return await call_next(request)
```

**Configuration**:
```python
LGDL_RATE_LIMIT_ENABLED=true
LGDL_RATE_LIMIT_USER=10/minute
LGDL_RATE_LIMIT_CONVERSATION=20/minute
LGDL_RATE_LIMIT_GLOBAL=1000/minute
```

**Tests**:
- test_user_rate_limit_enforced
- test_conversation_rate_limit_enforced
- test_rate_limit_reset_after_window
- test_rate_limit_bypass_for_admin
- test_429_response_with_retry_after

---

### Task 3.2: Circuit Breakers

**File**: `lgdl/runtime/circuit_breaker.py` (new, ~80 lines)

**Pattern**: Prevent cascade failures

**Implementation**:
```python
from enum import Enum

class CircuitState(Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery

class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        expected_exception: type = Exception
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None

    async def call(self, func, *args, **kwargs):
        """Execute function through circuit breaker"""
        if self.state == CircuitState.OPEN:
            # Check if recovery timeout passed
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
            else:
                raise CircuitBreakerOpen("Circuit breaker is OPEN")

        try:
            result = await func(*args, **kwargs)

            # Success - reset if HALF_OPEN
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.CLOSED
                self.failure_count = 0

            return result

        except self.expected_exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                print(f"[Circuit] OPEN after {self.failure_count} failures")

            raise
```

**Usage**:
```python
# Storage circuit breaker
storage_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=30.0)

async def load_conversation_safe(conversation_id):
    try:
        return await storage_breaker.call(
            storage.load_conversation,
            conversation_id
        )
    except CircuitBreakerOpen:
        # Graceful degradation - return None
        print("[Storage] Circuit OPEN, degrading to stateless mode")
        return None
```

**Metrics**:
- Circuit state changes
- Failure counts
- Recovery time
- Calls rejected while OPEN

**Tests**:
- test_circuit_opens_after_threshold
- test_circuit_half_open_after_timeout
- test_circuit_closes_on_success
- test_circuit_rejects_when_open
- test_multiple_circuit_breakers

---

### Task 3.3: TTL Enforcement & Cleanup

**File**: `lgdl/runtime/storage/cleanup.py` (new, ~60 lines)

**Background Task**: Periodic cleanup of old conversations

**Implementation**:
```python
import asyncio
from datetime import timedelta

class ConversationCleaner:
    def __init__(
        self,
        storage: StorageBackend,
        retention_days: int = 30,
        interval_hours: int = 24
    ):
        self.storage = storage
        self.retention = timedelta(days=retention_days)
        self.interval = interval_hours * 3600
        self._task = None

    async def start(self):
        """Start background cleanup task"""
        self._task = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self):
        while True:
            try:
                count = await self.storage.cleanup_old_conversations(self.retention)
                print(f"[Cleanup] Removed {count} conversations older than {self.retention.days} days")
            except Exception as e:
                print(f"[Cleanup] Error: {e}")

            await asyncio.sleep(self.interval)

    async def stop(self):
        if self._task:
            self._task.cancel()
```

**Integration**: Start on API startup
```python
@app.on_event("startup")
async def startup():
    cleaner = ConversationCleaner(storage, retention_days=30)
    await cleaner.start()
```

**Configuration**:
```python
LGDL_CONVERSATION_TTL_DAYS=30
LGDL_CLEANUP_INTERVAL_HOURS=24
LGDL_CLEANUP_ENABLED=true
```

**Tests**:
- test_cleanup_old_conversations
- test_cleanup_respects_retention
- test_cleanup_runs_periodically
- test_cleanup_handles_errors

---

### Task 3.4: Graceful Degradation

**File**: `lgdl/runtime/engine.py` (modify, +60 lines)

**Strategy**: Continue serving requests even if state/slots unavailable

**Implementation**:
```python
async def process_turn(...):
    # Try to load state
    state = None
    degraded = False

    try:
        if self.state_manager:
            state = await self.state_manager.get_or_create(conversation_id)
    except Exception as e:
        print(f"[Degradation] State unavailable: {e}")
        degraded = True
        state = None  # Continue without state

    # Disable state-dependent features if degraded
    if degraded:
        # Skip context enrichment
        # Skip slot-filling
        # Log warning

    # Continue with pattern matching and response
    # Return with degraded=true flag

    return {
        "move_id": mv["id"],
        "response": response,
        "degraded": degraded,  # NEW flag
        ...
    }
```

**Degradation Levels**:
1. **No state**: Continue with pattern matching only
2. **No slots**: Skip slot-filling, use regular blocks
3. **No capabilities**: Return canned responses

**Configuration**:
```python
LGDL_DEGRADATION_ENABLED=true
LGDL_DEGRADATION_LOG_LEVEL=warn
```

**Tests**:
- test_graceful_degradation_no_state
- test_graceful_degradation_no_slots
- test_degraded_flag_in_response
- test_metrics_track_degradation

---

## Phase 4: Monitoring & Observability

**Duration**: 1 week (Days 21-25)
**Effort**: ~400 lines of code, 5 tests
**Priority**: Medium (operational visibility)

### Task 4.1: Metrics Collection

**File**: `lgdl/runtime/monitoring.py` (new, ~200 lines)

**Metrics Categories**:

1. **Conversation Metrics**:
   - `conversations_created_total` (counter)
   - `conversations_active` (gauge)
   - `conversation_duration_seconds` (histogram)
   - `turns_per_conversation` (histogram)
   - `conversation_completion_rate` (gauge)

2. **Performance Metrics**:
   - `turn_latency_seconds` (histogram with quantiles)
   - `state_read_latency_seconds` (histogram)
   - `state_write_latency_seconds` (histogram)
   - `pattern_match_latency_seconds` (histogram)
   - `capability_call_latency_seconds` (histogram)

3. **Slot-Filling Metrics**:
   - `slots_filled_total` (counter by slot_name)
   - `slot_validation_failures_total` (counter)
   - `slot_prompts_per_conversation` (histogram)
   - `slot_fill_time_seconds` (histogram)

4. **System Metrics**:
   - `memory_usage_bytes` (gauge)
   - `cache_hit_rate` (gauge)
   - `storage_pool_size` (gauge)
   - `circuit_breaker_state` (gauge)

5. **Error Metrics**:
   - `errors_total` (counter by type)
   - `rate_limit_rejections_total` (counter)
   - `degraded_responses_total` (counter)

**Implementation**:
```python
class MetricsCollector:
    def __init__(self):
        self.counters: Dict[str, int] = {}
        self.gauges: Dict[str, float] = {}
        self.histograms: Dict[str, List[float]] = {}

    def increment(self, name: str, value: int = 1, labels: Dict = None):
        """Increment counter"""

    def set_gauge(self, name: str, value: float, labels: Dict = None):
        """Set gauge value"""

    def observe(self, name: str, value: float, labels: Dict = None):
        """Record histogram observation"""

    def get_metrics(self) -> Dict:
        """Get all metrics in Prometheus format"""

# Global instance
metrics = MetricsCollector()
```

**Integration**:
```python
# In engine.py
metrics.increment("turns_total", labels={"game_id": game_id, "move_id": move_id})
metrics.observe("turn_latency_seconds", duration)
metrics.set_gauge("active_conversations", len(state_manager.active))
```

**Tests**:
- test_counter_increment
- test_gauge_set
- test_histogram_observe
- test_percentile_calculation
- test_label_filtering

---

### Task 4.2: Prometheus Exporter

**File**: `lgdl/runtime/exporters/prometheus.py` (new, ~80 lines)

**Endpoint**: `GET /metrics`

**Implementation**:
```python
from prometheus_client import Counter, Gauge, Histogram, generate_latest, REGISTRY

# Define metrics
turns_total = Counter(
    'lgdl_turns_total',
    'Total turns processed',
    ['game_id', 'move_id']
)

turn_latency = Histogram(
    'lgdl_turn_latency_seconds',
    'Turn processing latency',
    ['game_id'],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

active_conversations = Gauge(
    'lgdl_active_conversations',
    'Currently active conversations',
    ['game_id']
)

# Export endpoint
@app.get("/metrics")
async def prometheus_metrics():
    return Response(
        content=generate_latest(REGISTRY),
        media_type="text/plain"
    )
```

**Prometheus Config** (`deploy/prometheus/lgdl.yml`):
```yaml
scrape_configs:
  - job_name: 'lgdl'
    scrape_interval: 15s
    static_configs:
      - targets: ['localhost:9000']
```

**Metrics Exposed**:
```
# TYPE lgdl_turns_total counter
lgdl_turns_total{game_id="medical",move_id="pain_assessment"} 1234

# TYPE lgdl_turn_latency_seconds histogram
lgdl_turn_latency_seconds_bucket{game_id="medical",le="0.5"} 950
lgdl_turn_latency_seconds_sum{game_id="medical"} 342.5
lgdl_turn_latency_seconds_count{game_id="medical"} 1000

# TYPE lgdl_active_conversations gauge
lgdl_active_conversations{game_id="medical"} 42
```

**Dependencies**: `prometheus-client>=0.20.0`

**Tests**:
- test_metrics_endpoint_format
- test_counter_exposed
- test_histogram_buckets
- test_label_filtering

---

### Task 4.3: Grafana Dashboard

**File**: `deploy/grafana/lgdl_dashboard.json` (new, ~60 lines)

**Panels**:

1. **Overview Row**:
   - Total conversations (24h)
   - Total turns (24h)
   - Active conversations (now)
   - Error rate (1h)

2. **Latency Row**:
   - Turn latency P50/P95/P99 (graph over time)
   - State read latency (graph)
   - State write latency (graph)
   - Capability call latency (graph)

3. **Slot-Filling Row**:
   - Slots filled per hour (graph)
   - Validation failures (graph)
   - Average prompts per conversation (gauge)

4. **System Health Row**:
   - Memory usage (graph)
   - Cache hit rate (gauge)
   - Circuit breaker states (status panel)
   - Rate limit rejections (graph)

**Alerts**:
- P95 latency > 500ms for 5 minutes
- Error rate > 5% for 5 minutes
- Active conversations > 200
- Memory usage > 80%

**Export**: JSON for import into Grafana

---

### Task 4.4: CloudWatch Exporter (Optional - AWS only)

**File**: `lgdl/runtime/exporters/cloudwatch.py` (new, ~60 lines)

**Implementation**:
```python
import boto3

class CloudWatchExporter:
    def __init__(self, namespace: str = "LGDL/Production"):
        self.cloudwatch = boto3.client('cloudwatch')
        self.namespace = namespace

    async def publish_metrics(self, metrics: Dict):
        """Batch publish metrics to CloudWatch"""
        metric_data = []

        for name, value in metrics.items():
            metric_data.append({
                'MetricName': name,
                'Value': value,
                'Unit': 'Count',  # or 'Seconds', 'Bytes'
                'Timestamp': datetime.utcnow()
            })

        self.cloudwatch.put_metric_data(
            Namespace=self.namespace,
            MetricData=metric_data
        )
```

**Metrics**:
- TurnLatency (Milliseconds, P95)
- ConversationsActive (Count)
- ErrorRate (Percent)
- SlotsFilled (Count)

**Configuration**:
```python
LGDL_CLOUDWATCH_ENABLED=false
LGDL_CLOUDWATCH_NAMESPACE=LGDL/Production
LGDL_CLOUDWATCH_REGION=us-east-1
```

**Dependencies**: `boto3>=1.28.0` (if AWS)

---

## Phase 5: Load Testing

**Duration**: 2 days (Days 26-27)
**Effort**: ~200 lines of code
**Priority**: High (validates performance)

### Task 5.1: Locust Test Scenarios

**File**: `tests/load/locustfile.py` (new, ~150 lines)

**Scenarios**:

1. **Simple Turn** (baseline):
```python
class SimpleTurnUser(HttpUser):
    wait_time = between(1, 3)

    @task
    def single_turn(self):
        self.client.post("/games/medical/move", json={
            "conversation_id": str(uuid.uuid4()),
            "user_id": "load_test_user",
            "input": "I need an appointment"
        })
```

2. **Multi-Turn Conversation**:
```python
class MultiTurnUser(HttpUser):
    def on_start(self):
        self.conversation_id = str(uuid.uuid4())

    @task
    def multi_turn_dialog(self):
        # Turn 1
        self.client.post("/games/medical/move", json={
            "conversation_id": self.conversation_id,
            "user_id": "load_test_user",
            "input": "I'm in pain"
        })
        # Turn 2-4: continue dialog
        ...
```

3. **Slot-Filling Load**:
```python
class SlotFillingUser(HttpUser):
    @task
    def pain_assessment(self):
        conv_id = str(uuid.uuid4())

        # Progressive 4-turn pain assessment
        inputs = ["I'm in pain", "chest", "8", "an hour ago"]
        for inp in inputs:
            self.client.post("/games/medical/move", json={
                "conversation_id": conv_id,
                "user_id": "load_test_user",
                "input": inp
            })
            time.sleep(0.5)  # Simulate user thinking
```

4. **Sustained Load**:
```python
class SustainedLoadUser(HttpUser):
    wait_time = constant(1)  # 1 request per second per user

    @task(weight=7)
    def short_conversation(self):
        # 1-2 turns

    @task(weight=3)
    def long_conversation(self):
        # 5-10 turns
```

**Load Profiles**:
```bash
# Smoke test: 10 users, 1 minute
locust -f locustfile.py --users 10 --spawn-rate 2 --run-time 1m --host http://localhost:9000

# Load test: 100 users, 30 minutes
locust -f locustfile.py --users 100 --spawn-rate 10 --run-time 30m

# Stress test: 200 users, ramp up
locust -f locustfile.py --users 200 --spawn-rate 20 --run-time 60m
```

**Metrics to Track**:
- Requests per second (RPS)
- P50/P95/P99 latency
- Error rate
- Active conversations
- Database connection pool saturation

**Targets**:
- 100 concurrent conversations: P95 < 500ms
- 200 concurrent conversations: P95 < 1000ms
- Error rate: < 1%
- No memory leaks over 60 minute test

---

### Task 5.2: Chaos Engineering

**File**: `tests/load/chaos.py` (new, ~50 lines)

**Scenarios**:

1. **Database Failure**:
   - Kill PostgreSQL mid-conversation
   - Verify circuit breaker opens
   - Verify graceful degradation

2. **Redis Failure**:
   - Kill Redis cache
   - Verify fallback to PostgreSQL
   - Verify latency increase but no errors

3. **Network Latency**:
   - Inject 100ms delay to database
   - Verify P95 latency stays under target
   - Verify timeouts work correctly

4. **Memory Pressure**:
   - Limit container memory
   - Verify no OOM crashes
   - Verify cache eviction works

5. **CPU Throttling**:
   - Limit CPU to 50%
   - Verify throughput degradation is graceful
   - Verify no request timeouts

**Tools**: chaos-mesh, toxiproxy, or custom scripts

**Validation**:
- System continues serving requests
- Circuit breakers trigger correctly
- Graceful degradation activates
- Recovery automatic after issue resolved

---

## Phase 6: Security Hardening

**Duration**: 1 week (Days 28-32)
**Effort**: ~300 lines of code, 10 tests
**Priority**: Medium (compliance requirement)

### Task 6.1: State Encryption at Rest

**File**: `lgdl/runtime/encryption.py` (new, ~100 lines)

**Algorithm**: AES-256-GCM with envelope encryption

**Implementation**:
```python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os

class StateEncryptor:
    def __init__(self, key: bytes):
        """Initialize with 256-bit key"""
        self.cipher = AESGCM(key)

    def encrypt(self, plaintext: str) -> bytes:
        """Encrypt with random nonce"""
        nonce = os.urandom(12)
        ciphertext = self.cipher.encrypt(nonce, plaintext.encode(), None)
        return nonce + ciphertext  # Prepend nonce

    def decrypt(self, encrypted: bytes) -> str:
        """Decrypt with nonce from data"""
        nonce = encrypted[:12]
        ciphertext = encrypted[12:]
        plaintext = self.cipher.decrypt(nonce, ciphertext, None)
        return plaintext.decode()
```

**Integration**: Transparent encryption in storage layer
```python
class EncryptedStorage(StorageBackend):
    def __init__(self, backend: StorageBackend, encryptor: StateEncryptor):
        self.backend = backend
        self.encryptor = encryptor

    async def save_conversation(self, state):
        # Encrypt sensitive fields
        encrypted_state = self._encrypt_sensitive_fields(state)
        await self.backend.save_conversation(encrypted_state)
```

**Encrypted Fields**:
- `user_input` (may contain PII)
- `extracted_params` (may contain sensitive data)
- `slot_values` (may contain personal information)

**Key Management**:
- Environment variable (dev/test)
- AWS KMS (production)
- Key rotation support

**Configuration**:
```python
LGDL_ENCRYPTION_ENABLED=false  # Optional feature
LGDL_ENCRYPTION_KEY=<base64-encoded-key>
LGDL_ENCRYPTION_KMS_KEY_ID=<aws-kms-key-id>
```

**Tests**:
- test_encryption_roundtrip
- test_key_rotation
- test_decrypt_with_old_key
- test_performance_overhead (< 5ms)

**Dependencies**: `cryptography>=42.0.0`

---

### Task 6.2: PII Redaction

**File**: `lgdl/runtime/pii.py` (new, ~100 lines)

**Detection Patterns**:
```python
PII_PATTERNS = {
    "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    "phone": r'\b(\+\d{1,2}\s?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b',
    "ssn": r'\b\d{3}-\d{2}-\d{4}\b',
    "credit_card": r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',
    "name": r'\b(Dr\.|Mr\.|Mrs\.|Ms\.)\s+[A-Z][a-z]+\b'  # Simplified
}
```

**Implementation**:
```python
class PIIRedactor:
    def redact_for_logs(self, text: str) -> str:
        """Redact PII for logging (irreversible)"""
        for pii_type, pattern in PII_PATTERNS.items():
            text = re.sub(pattern, f'<{pii_type.upper()}_REDACTED>', text)
        return text

    def tokenize_for_storage(self, text: str) -> Tuple[str, Dict]:
        """Tokenize PII for storage (reversible)"""
        tokens = {}
        def replacer(match):
            token_id = str(uuid.uuid4())[:8]
            tokens[token_id] = match.group(0)
            return f'<TOKEN:{token_id}>'

        redacted = re.sub(pattern, replacer, text)
        return redacted, tokens

    def detokenize(self, text: str, tokens: Dict) -> str:
        """Restore original PII (authorized access only)"""
        for token_id, original in tokens.items():
            text = text.replace(f'<TOKEN:{token_id}>', original)
        return text
```

**Integration**:
```python
# Redact in logs
print(f"[Turn] Input: {pii_redactor.redact_for_logs(user_input)}")

# Tokenize for storage
tokenized, tokens = pii_redactor.tokenize_for_storage(user_input)
# Store tokenized text + tokens separately (encrypted)
```

**Configuration**:
```python
LGDL_PII_REDACTION_ENABLED=true
LGDL_PII_REDACT_IN_LOGS=true
LGDL_PII_TOKENIZE_IN_STORAGE=false  # Optional, needs encryption
```

**Tests**:
- test_email_redaction
- test_phone_redaction
- test_tokenization_roundtrip
- test_log_redaction
- test_multiple_pii_types

---

### Task 6.3: GDPR Compliance

**File**: `lgdl/runtime/gdpr.py` (new, ~50 lines)

**Features**:

1. **Right to Erasure** (Right to be Forgotten):
```python
@app.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, user_id: str):
    # Verify user owns conversation
    # Delete all data (CASCADE handles slots, turns, context)
    await storage.delete_conversation(conversation_id)

    # Audit log
    await audit_log.log("conversation_deleted", {
        "conversation_id": conversation_id,
        "user_id": user_id,
        "timestamp": datetime.utcnow()
    })
```

2. **Data Export** (Right to Data Portability):
```python
@app.get("/conversations/{conversation_id}/export")
async def export_conversation(conversation_id: str, user_id: str):
    # Verify user owns conversation
    state = await storage.load_conversation(conversation_id)

    # Export all data in structured format
    return {
        "conversation_id": conversation_id,
        "created_at": state.created_at,
        "turns": [turn.to_dict() for turn in state.turns_history],
        "extracted_context": state.extracted_context,
        "slots": await get_all_slots(conversation_id),
        "format_version": "1.0"
    }
```

3. **Consent Tracking**:
```python
# Add to PersistentState
consent_given: bool = False
consent_timestamp: Optional[datetime] = None

# Require consent before processing
if not state.consent_given:
    return {"error": "Consent required", "code": "E901"}
```

4. **Retention Policy**:
```python
# Automatic deletion after retention period
LGDL_GDPR_RETENTION_DAYS=90
# Weekly cleanup job deletes data older than retention
```

**Tests**:
- test_delete_conversation_cascade
- test_export_conversation_format
- test_consent_enforcement
- test_retention_policy

---

### Task 6.4: Audit Logging

**File**: `lgdl/runtime/audit.py` (new, ~50 lines)

**Logged Events**:
```python
class AuditLogger:
    async def log(self, event_type: str, data: Dict):
        """Write audit log entry"""
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type,
            "data": data
        }

        # Write to separate audit log file (append-only)
        await self._write_to_audit_log(entry)

        # Optionally send to SIEM
        if SIEM_ENABLED:
            await self._send_to_siem(entry)

# Events to log
- conversation_created
- conversation_accessed
- conversation_deleted
- pii_accessed
- capability_called
- rate_limit_exceeded
- authentication_failed
- encryption_key_rotated
```

**Audit Log Format** (`/var/log/lgdl/audit.log`):
```json
{"timestamp":"2025-10-31T12:00:00Z","event":"conversation_deleted","user_id":"user123","conversation_id":"conv456"}
{"timestamp":"2025-10-31T12:05:00Z","event":"pii_accessed","user_id":"admin","conversation_id":"conv789","reason":"support_ticket"}
```

**Configuration**:
```python
LGDL_AUDIT_ENABLED=true
LGDL_AUDIT_LOG_PATH=/var/log/lgdl/audit.log
LGDL_AUDIT_SIEM_URL=<siem-endpoint>
```

**Tests**:
- test_audit_log_written
- test_audit_log_format
- test_sensitive_events_logged

---

## Phase 7: Deployment & Infrastructure

**Duration**: 1 week (Days 33-37)
**Effort**: ~400 lines of config/code
**Priority**: High (deployment enablement)

### Task 7.1: Docker Deployment

**File**: `Dockerfile` (new, ~50 lines)

```dockerfile
# Multi-stage build
FROM python:3.13-slim AS builder

WORKDIR /app

# Install uv
RUN pip install uv

# Copy dependencies
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

# Copy application
COPY lgdl/ lgdl/
COPY examples/ examples/

# Runtime stage
FROM python:3.13-slim

WORKDIR /app

# Non-root user
RUN useradd -m -u 1000 lgdl

# Copy from builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/lgdl /app/lgdl
COPY --from=builder /app/examples /app/examples

# Switch to non-root
USER lgdl

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:9000/healthz || exit 1

# Run
ENV PATH="/app/.venv/bin:$PATH"
CMD ["uvicorn", "lgdl.runtime.api:app", "--host", "0.0.0.0", "--port", "9000"]
```

**File**: `docker-compose.yml` (new, ~80 lines)

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: lgdl
      POSTGRES_USER: lgdl
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "lgdl"]
      interval: 10s

  redis:
    image: redis:7-alpine
    command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s

  lgdl:
    build: .
    ports:
      - "9000:9000"
    environment:
      LGDL_POSTGRES_URL: postgresql://lgdl:${POSTGRES_PASSWORD}@postgres:5432/lgdl
      LGDL_REDIS_URL: redis://redis:6379/0
      LGDL_STATE_DISABLED: "0"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/healthz"]
      interval: 30s

  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./deploy/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD}
    volumes:
      - ./deploy/grafana/dashboards:/etc/grafana/provisioning/dashboards
      - grafana_data:/var/lib/grafana

volumes:
  postgres_data:
  prometheus_data:
  grafana_data:
```

**Usage**:
```bash
# Start stack
docker-compose up -d

# View logs
docker-compose logs -f lgdl

# Scale API
docker-compose up -d --scale lgdl=3

# Stop
docker-compose down
```

---

### Task 7.2: Kubernetes Helm Chart

**File**: `deploy/helm/lgdl/Chart.yaml` (new)

```yaml
apiVersion: v2
name: lgdl
description: Language-Game Definition Language Runtime
version: 1.0.0
appVersion: "1.0"
```

**File**: `deploy/helm/lgdl/values.yaml` (new, ~100 lines)

```yaml
replicaCount: 2

image:
  repository: lgdl/runtime
  tag: "1.0-rc"
  pullPolicy: IfNotPresent

service:
  type: ClusterIP
  port: 9000

ingress:
  enabled: true
  className: nginx
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
  hosts:
    - host: lgdl.example.com
      paths:
        - path: /
          pathType: Prefix

resources:
  limits:
    cpu: 1000m
    memory: 512Mi
  requests:
    cpu: 200m
    memory: 256Mi

autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70
  targetMemoryUtilizationPercentage: 80

postgresql:
  enabled: true
  auth:
    database: lgdl
    username: lgdl
  primary:
    persistence:
      enabled: true
      size: 10Gi

redis:
  enabled: true
  architecture: standalone
  auth:
    enabled: false
  master:
    persistence:
      enabled: false

monitoring:
  prometheus:
    enabled: true
  grafana:
    enabled: true
```

**File**: `deploy/helm/lgdl/templates/deployment.yaml` (new, ~80 lines)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "lgdl.fullname" . }}
spec:
  replicas: {{ .Values.replicaCount }}
  selector:
    matchLabels:
      app: lgdl
  template:
    metadata:
      labels:
        app: lgdl
    spec:
      containers:
      - name: lgdl
        image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
        ports:
        - containerPort: 9000
        env:
        - name: LGDL_POSTGRES_URL
          valueFrom:
            secretKeyRef:
              name: lgdl-db-secret
              key: postgres-url
        - name: LGDL_REDIS_URL
          value: "redis://{{ .Release.Name }}-redis-master:6379/0"
        livenessProbe:
          httpGet:
            path: /healthz
            port: 9000
          initialDelaySeconds: 10
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /healthz
            port: 9000
          initialDelaySeconds: 5
          periodSeconds: 10
        resources:
          {{- toYaml .Values.resources | nindent 12 }}
```

**Installation**:
```bash
# Install
helm install lgdl ./deploy/helm/lgdl \
  --set postgresql.auth.password=secret \
  --namespace lgdl --create-namespace

# Upgrade
helm upgrade lgdl ./deploy/helm/lgdl \
  --reuse-values \
  --set image.tag=1.0

# Status
helm status lgdl -n lgdl

# Uninstall
helm uninstall lgdl -n lgdl
```

---

### Task 7.3: CI/CD Pipeline

**File**: `.github/workflows/production.yml` (new, ~70 lines)

```yaml
name: Production Deployment

on:
  push:
    tags:
      - 'v*'

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v1
      - run: uv sync --extra dev
      - run: uv run pytest tests/ -v

  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/build-push-action@v5
        with:
          push: true
          tags: lgdl/runtime:${{ github.ref_name }}

  security-scan:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: aquasecurity/trivy-action@master
        with:
          image-ref: lgdl/runtime:${{ github.ref_name }}
          format: 'sarif'
          output: 'trivy-results.sarif'

  deploy-staging:
    needs: [build, security-scan]
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - run: |
          helm upgrade lgdl-staging ./deploy/helm/lgdl \
            --install \
            --namespace lgdl-staging \
            --set image.tag=${{ github.ref_name }}

  load-test-staging:
    needs: deploy-staging
    runs-on: ubuntu-latest
    steps:
      - run: |
          locust -f tests/load/locustfile.py \
            --users 100 --spawn-rate 10 --run-time 5m \
            --host https://staging.lgdl.example.com \
            --headless --only-summary

  deploy-production:
    needs: load-test-staging
    runs-on: ubuntu-latest
    environment: production
    steps:
      - run: |
          helm upgrade lgdl ./deploy/helm/lgdl \
            --install \
            --namespace lgdl \
            --set image.tag=${{ github.ref_name }}
```

**Features**:
- Automated testing before deployment
- Security scanning with Trivy
- Staging deployment with load testing
- Production deployment (manual approval)
- Rollback on failure

---

## Phase 8: Documentation

**Duration**: 1 week (Days 38-42)
**Effort**: ~500 lines of documentation
**Priority**: Medium (operational enablement)

### Task 8.1: Deployment Guide

**File**: `docs/DEPLOYMENT.md` (new, ~200 lines)

**Sections**:

1. **Prerequisites**
   - Docker / Kubernetes
   - PostgreSQL / Redis
   - Resource requirements

2. **Local Development**
   ```bash
   # SQLite (default)
   uv run lgdl serve --games medical:examples/medical/game.lgdl
   ```

3. **Docker Deployment**
   ```bash
   # Build
   docker build -t lgdl:1.0 .

   # Run with docker-compose
   docker-compose up -d

   # Verify
   curl http://localhost:9000/healthz
   ```

4. **Kubernetes Deployment**
   ```bash
   # Install with Helm
   helm install lgdl ./deploy/helm/lgdl \
     --namespace lgdl --create-namespace

   # Verify
   kubectl get pods -n lgdl
   kubectl logs -f deployment/lgdl -n lgdl
   ```

5. **Configuration Reference**
   - Environment variables
   - Storage backends
   - Monitoring setup
   - Security options

6. **Scaling Guidelines**
   - Horizontal scaling (replica count)
   - Vertical scaling (resource limits)
   - Database sizing
   - Redis memory limits

7. **Backup & Recovery**
   - PostgreSQL backup strategy
   - Restore procedures
   - Disaster recovery RTO/RPO

---

### Task 8.2: Monitoring Runbook

**File**: `docs/MONITORING.md` (new, ~150 lines)

**Sections**:

1. **Metrics Reference**
   - Conversation metrics
   - Performance metrics
   - Slot-filling metrics
   - System metrics
   - Error metrics

2. **Alert Rules**
   ```yaml
   # Prometheus alert rules
   groups:
     - name: lgdl_alerts
       rules:
         - alert: HighLatency
           expr: lgdl_turn_latency_seconds{quantile="0.95"} > 0.5
           for: 5m
           annotations:
             summary: "P95 latency above 500ms"

         - alert: HighErrorRate
           expr: rate(lgdl_errors_total[5m]) > 0.05
           for: 5m
           annotations:
             summary: "Error rate above 5%"
   ```

3. **Troubleshooting by Symptom**

   **High Latency**:
   - Check database connection pool saturation
   - Check slow queries in PostgreSQL
   - Check Redis memory usage
   - Check pattern cache hit rate

   **High Error Rate**:
   - Check circuit breaker state
   - Check database connectivity
   - Check capability timeouts
   - Review error logs

   **Memory Growth**:
   - Check for conversation leaks
   - Check cache size limits
   - Check connection pool size

4. **Incident Response**
   - Severity classification
   - Escalation procedures
   - Runbook by incident type

5. **Capacity Planning**
   - Current usage metrics
   - Growth projections
   - Scaling recommendations

---

### Task 8.3: Troubleshooting Guide

**File**: `docs/TROUBLESHOOTING.md` (new, ~150 lines)

**Common Issues**:

1. **Slot-Filling Not Working**

   **Symptom**: Slots not persisting, prompts repeating

   **Diagnosis**:
   ```bash
   # Check state manager enabled
   curl http://localhost:9000/healthz
   # Should show: "state_enabled": true

   # Check database
   sqlite3 ~/.lgdl/conversations.db "SELECT * FROM slots;"

   # Check logs
   docker logs lgdl | grep "\[Slot\]"
   ```

   **Resolution**:
   - Verify LGDL_STATE_DISABLED=0
   - Check database connectivity
   - Restart server to run migration

2. **High Database Latency**

   **Symptom**: P95 latency > 500ms

   **Diagnosis**:
   ```sql
   -- PostgreSQL slow queries
   SELECT query, mean_exec_time, calls
   FROM pg_stat_statements
   ORDER BY mean_exec_time DESC LIMIT 10;

   -- Check indexes
   SELECT schemaname, tablename, indexname
   FROM pg_indexes WHERE schemaname = 'public';
   ```

   **Resolution**:
   - Add missing indexes
   - Optimize queries
   - Scale database (read replicas)
   - Enable connection pooling

3. **Circuit Breaker Open**

   **Symptom**: "Circuit breaker is OPEN" errors

   **Diagnosis**:
   ```bash
   # Check circuit state
   curl http://localhost:9000/metrics | grep circuit_breaker_state

   # Check underlying service
   curl http://postgres:5432  # Should be accessible
   ```

   **Resolution**:
   - Fix underlying service issue
   - Wait for recovery timeout (30s default)
   - Reset circuit breaker manually (if needed)

4. **Rate Limit Exceeded**

   **Symptom**: 429 responses

   **Diagnosis**:
   ```bash
   # Check rate limit config
   env | grep LGDL_RATE_LIMIT

   # Check Redis keys
   redis-cli KEYS "ratelimit:*"
   ```

   **Resolution**:
   - Adjust rate limits
   - Implement user authentication
   - Add rate limit bypass for admin

---

## Implementation Timeline

### Week-by-Week Breakdown

| Week | Phase | Deliverables | Status |
|------|-------|--------------|--------|
| **1-2** | Storage Backends | Redis, PostgreSQL, migration | 🚧 Planning |
| **3** | Performance | Caching, pooling, monitoring | 🚧 Planning |
| **4** | Safety | Rate limiting, circuit breakers | 🚧 Planning |
| **5** | Monitoring | Prometheus, Grafana, metrics | 🚧 Planning |
| **6 (Days 1-2)** | Load Testing | Locust, chaos engineering | 🚧 Planning |
| **6-7** | Security | Encryption, PII, GDPR, audit | 🚧 Planning |
| **8** | Deployment | Docker, K8s, CI/CD | 🚧 Planning |
| **8-9** | Documentation | Guides, runbooks | 🚧 Planning |
| **9-10** | Buffer | Fixes, optimization, polish | 🚧 Planning |

### Critical Path

```
Week 1-2: Storage → Week 3: Performance → Week 4: Safety → Week 6: Load Test
                                                                    ↓
                                                           Week 9-10: Fix Issues
                                                                    ↓
                                                              v1.0 Production
```

**Parallel Work**:
- Week 5: Monitoring (can parallelize with Week 6-7)
- Week 6-7: Security (can parallelize with Week 8)
- Week 8: Deployment (can parallelize with documentation)

---

## Dependencies & Requirements

### New Python Dependencies

```toml
# Production storage
redis = { version = ">=5.0.0", extras = ["asyncio"] }
asyncpg = ">=0.29.0"

# Monitoring
prometheus-client = ">=0.20.0"
boto3 = { version = ">=1.28.0", optional = true }  # For CloudWatch

# Load testing
locust = { version = ">=2.20.0", optional = true }

# Security
cryptography = ">=42.0.0"

# Deployment (dev only)
docker = { version = ">=7.0.0", optional = true }
```

### Infrastructure Requirements

**Development**:
- SQLite (included)
- No external dependencies

**Staging**:
- PostgreSQL 16+ (1 vCPU, 2GB RAM)
- Redis 7+ (256MB memory)
- 2 API instances (0.5 vCPU, 512MB each)

**Production**:
- PostgreSQL 16+ (2 vCPU, 4GB RAM, read replica recommended)
- Redis 7+ cluster (1GB memory, replication)
- API instances (2-10 pods, 1 vCPU, 512MB each)
- Prometheus (1 vCPU, 1GB RAM)
- Grafana (0.5 vCPU, 512MB)

**Cost Estimate** (AWS t3/t4g):
- Staging: ~$50/month
- Production: ~$200-400/month (depending on scale)

---

## Risks & Mitigation

### Technical Risks

1. **Redis/PostgreSQL Complexity**
   - **Risk**: Integration issues, migration bugs
   - **Mitigation**: Thorough testing, SQLite remains default, phased rollout
   - **Fallback**: Keep SQLite as option for low-scale deployments

2. **Load Testing Reveals Performance Issues**
   - **Risk**: Can't meet <500ms P95 latency target
   - **Mitigation**: 2-week buffer (Week 9-10) for optimization
   - **Fallback**: Adjust target based on real-world constraints

3. **Security Audit Finds Vulnerabilities**
   - **Risk**: Delays release for remediation
   - **Mitigation**: Security hardening in Week 7, external audit in Week 10
   - **Fallback**: Document known issues, plan v1.1 fixes

4. **K8s Deployment Complexity**
   - **Risk**: Helm chart issues, networking problems
   - **Mitigation**: Test in staging first, comprehensive docs
   - **Fallback**: Docker Compose for simpler deployments

### Operational Risks

1. **Insufficient Documentation**
   - **Risk**: Operators can't deploy/troubleshoot
   - **Mitigation**: Dedicated Week 8 for docs, runbooks
   - **Fallback**: On-demand documentation as issues arise

2. **Migration Data Loss**
   - **Risk**: SQLite → PostgreSQL migration corrupts data
   - **Mitigation**: Dry-run mode, verification step, backups
   - **Fallback**: Keep SQLite running in parallel during migration

3. **Monitoring Gaps**
   - **Risk**: Missing critical metrics, blind spots
   - **Mitigation**: Comprehensive metrics in Week 5, load testing validates
   - **Fallback**: Add metrics post-release as needed

---

## Success Criteria

### Technical Criteria

**Storage**:
- ✅ Redis backend operational with <5ms read latency
- ✅ PostgreSQL backend operational with <10ms read, <20ms write
- ✅ Migration tooling successfully migrates 10,000+ conversations

**Performance**:
- ✅ P95 latency <500ms at 100 concurrent conversations
- ✅ P99 latency <1000ms at 100 concurrent conversations
- ✅ Cache hit rate >90% for warm patterns
- ✅ Connection pooling reduces connection overhead by 50%

**Safety**:
- ✅ Rate limiting blocks abusive users (>100 req/min)
- ✅ Circuit breaker opens after 5 consecutive failures
- ✅ Graceful degradation serves requests when state unavailable
- ✅ TTL cleanup removes conversations after retention period

**Monitoring**:
- ✅ All key metrics exported to Prometheus
- ✅ Grafana dashboards show real-time system state
- ✅ Alerts trigger on P95 > 500ms, error rate > 5%

### Operational Criteria

**Deployment**:
- ✅ Docker deployment works with `docker-compose up`
- ✅ Kubernetes deployment works with `helm install`
- ✅ CI/CD pipeline deploys on git tag
- ✅ Zero-downtime rolling updates verified

**Load Testing**:
- ✅ 100 concurrent conversations: P95 <500ms, error rate <1%
- ✅ 200 concurrent conversations: P95 <1000ms, error rate <1%
- ✅ Sustained 1000 conversations/hour for 24 hours: no memory leaks
- ✅ Chaos testing: system recovers from database failures

**Documentation**:
- ✅ Deployment guide covers Docker, K8s, configuration
- ✅ Monitoring runbook covers alerts, troubleshooting
- ✅ Troubleshooting guide covers common issues
- ✅ API documentation updated for production features

### Security Criteria

**Hardening**:
- ✅ PII redaction in logs (no emails, phones, SSN in logs)
- ✅ State encryption operational (optional but working)
- ✅ GDPR compliance: delete, export, consent tracking
- ✅ Audit logging captures critical events
- ✅ Security scan (Trivy) passes with no high/critical vulnerabilities

---

## Deliverables Checklist

### Code Deliverables
- [ ] `lgdl/runtime/storage/redis.py` (150 lines)
- [ ] `lgdl/runtime/storage/postgres.py` (150 lines)
- [ ] `lgdl/runtime/storage/hybrid.py` (50 lines)
- [ ] `lgdl/runtime/storage/pooling.py` (80 lines)
- [ ] `lgdl/runtime/storage/cleanup.py` (60 lines)
- [ ] `lgdl/runtime/rate_limiter.py` (100 lines)
- [ ] `lgdl/runtime/circuit_breaker.py` (80 lines)
- [ ] `lgdl/runtime/monitoring.py` (200 lines)
- [ ] `lgdl/runtime/metrics.py` (30 lines)
- [ ] `lgdl/runtime/exporters/prometheus.py` (80 lines)
- [ ] `lgdl/runtime/exporters/cloudwatch.py` (60 lines, optional)
- [ ] `lgdl/runtime/encryption.py` (100 lines)
- [ ] `lgdl/runtime/pii.py` (100 lines)
- [ ] `lgdl/runtime/gdpr.py` (50 lines)
- [ ] `lgdl/runtime/audit.py` (50 lines)
- [ ] `lgdl/cli/migrate.py` (100 lines)
- [ ] Updates to `lgdl/runtime/matcher.py` (+50 lines)
- [ ] Updates to `lgdl/runtime/state.py` (+40 lines)
- [ ] Updates to `lgdl/runtime/engine.py` (+60 lines)

**Total**: ~1,640 lines of production code

### Test Deliverables
- [ ] `tests/test_redis_storage.py` (10 tests)
- [ ] `tests/test_postgres_storage.py` (10 tests)
- [ ] `tests/test_migration.py` (5 tests)
- [ ] `tests/test_rate_limiter.py` (8 tests)
- [ ] `tests/test_circuit_breaker.py` (6 tests)
- [ ] `tests/test_monitoring.py` (5 tests)
- [ ] `tests/test_encryption.py` (4 tests)
- [ ] `tests/test_pii_redaction.py` (5 tests)
- [ ] `tests/test_gdpr.py` (4 tests)
- [ ] `tests/load/locustfile.py` (load tests)
- [ ] `tests/load/chaos.py` (chaos tests)

**Total**: ~60 new tests

### Configuration Deliverables
- [ ] `Dockerfile` (50 lines)
- [ ] `docker-compose.yml` (80 lines)
- [ ] `deploy/helm/lgdl/Chart.yaml` (10 lines)
- [ ] `deploy/helm/lgdl/values.yaml` (100 lines)
- [ ] `deploy/helm/lgdl/templates/deployment.yaml` (80 lines)
- [ ] `deploy/helm/lgdl/templates/service.yaml` (30 lines)
- [ ] `deploy/helm/lgdl/templates/ingress.yaml` (40 lines)
- [ ] `deploy/prometheus/prometheus.yml` (50 lines)
- [ ] `deploy/grafana/lgdl_dashboard.json` (60 lines)
- [ ] `.github/workflows/production.yml` (70 lines)

**Total**: ~570 lines of config/infra

### Documentation Deliverables
- [ ] `docs/DEPLOYMENT.md` (200 lines)
- [ ] `docs/MONITORING.md` (150 lines)
- [ ] `docs/TROUBLESHOOTING.md` (150 lines)
- [ ] `docs/SECURITY.md` (100 lines, new)
- [ ] Update `README.md` with production info (+50 lines)

**Total**: ~650 lines of documentation

---

## Estimated Effort Summary

| Category | Lines | Tests | Duration |
|----------|-------|-------|----------|
| **Production Code** | 1,640 | 47 | 6 weeks |
| **Configuration** | 570 | - | 1 week |
| **Documentation** | 650 | - | 1 week |
| **Load Testing** | 200 | - | 2 days |
| **Buffer/Polish** | - | - | 2 weeks |
| **TOTAL** | **3,060** | **47** | **8-10 weeks** |

---

## Post-Release (v1.1+)

### Future Enhancements
1. **Advanced Slot-Filling**:
   - LLM-based entity extraction
   - Nested/complex slot types
   - Conditional slot requirements

2. **Advanced Storage**:
   - Multi-region replication
   - Sharding for massive scale
   - Time-series database for metrics

3. **Advanced Monitoring**:
   - Distributed tracing (OpenTelemetry)
   - User session replay
   - ML-based anomaly detection

4. **Advanced Security**:
   - mTLS for service-to-service
   - OAuth2/OIDC integration
   - Advanced PII detection (NER-based)

---

## Approval & Next Steps

### Prerequisites for Starting
- ✅ v1.0-RC complete (slot-filling working)
- ✅ All 218 tests passing
- ✅ Medical example demonstrates full multi-turn flow
- ✅ Git tag v1.0-rc created and pushed

### Recommended Start
**Phase 1: Production Storage Backends** (Week 1-2)
- Highest impact on scalability
- Blocks other optimizations
- Clear interface already defined (StorageBackend protocol)

### Alternative: Prioritized Subset
If full 8-10 week timeline is too long, consider:

**Minimal Production** (3-4 weeks):
1. PostgreSQL backend (1 week)
2. Connection pooling + rate limiting (1 week)
3. Basic monitoring (Prometheus + 5 key metrics) (3 days)
4. Docker deployment (2 days)
5. Load testing validation (2 days)

This delivers: Scalable storage, basic safety, deployment tooling

---

**Plan Status**: Ready for implementation
**Next Action**: Begin Phase 1 (Storage Backends) or prioritized subset
**Timeline**: 8-10 weeks to v1.0 production
**Current Status**: v1.0-RC (feature-complete, ready for hardening)
