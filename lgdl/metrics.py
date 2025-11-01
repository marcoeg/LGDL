"""
LGDL Metrics Collection

Tracks performance metrics for cascade matching, cost control, and system health.
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import statistics


@dataclass
class TurnMetrics:
    """Metrics for a single conversation turn."""
    stage: str  # "lexical", "embedding", "llm_semantic"
    confidence: float  # 0.0-1.0
    latency_ms: float  # Milliseconds
    cost_usd: float  # Dollars
    timestamp: float = field(default_factory=time.time)


class LGDLMetrics:
    """Centralized metrics collection for LGDL runtime.

    Tracks:
    - Cascade stage distribution (% lexical, embedding, LLM)
    - Cost per turn (average, P95, P99)
    - Latency per turn (P50, P95, P99)
    - Confidence scores by stage

    Example:
        metrics = LGDLMetrics()

        # Record each turn
        metrics.record_turn(
            stage="llm_semantic",
            confidence=0.88,
            latency_ms=220.0,
            cost_usd=0.008
        )

        # Get summary
        print(metrics.get_summary())
    """

    def __init__(self):
        """Initialize metrics collector."""
        self.turns: List[TurnMetrics] = []

        # Counters
        self.counters = {
            "turns_total": 0,
            "cascade_stage_lexical": 0,
            "cascade_stage_embedding": 0,
            "cascade_stage_llm_semantic": 0,
            "cascade_stage_none": 0,
        }

        # Histograms (for percentile calculation)
        self.histograms = {
            "latency_ms": [],
            "cost_per_turn": [],
            "confidence_scores": [],
        }

        # Per-stage metrics
        self.by_stage = defaultdict(lambda: {
            "count": 0,
            "latencies": [],
            "costs": [],
            "confidences": []
        })

    def record_turn(
        self,
        stage: str,
        confidence: float,
        latency_ms: float,
        cost_usd: float = 0.0
    ):
        """Record metrics for a conversation turn.

        Args:
            stage: Cascade stage that matched ("lexical", "embedding", "llm_semantic")
            confidence: Final confidence score (0.0-1.0)
            latency_ms: Turn processing latency in milliseconds
            cost_usd: Estimated cost in USD
        """
        # Create turn record
        turn = TurnMetrics(
            stage=stage,
            confidence=confidence,
            latency_ms=latency_ms,
            cost_usd=cost_usd
        )
        self.turns.append(turn)

        # Update counters
        self.counters["turns_total"] += 1
        stage_key = f"cascade_stage_{stage}"
        if stage_key in self.counters:
            self.counters[stage_key] += 1

        # Update histograms
        self.histograms["latency_ms"].append(latency_ms)
        self.histograms["cost_per_turn"].append(cost_usd)
        self.histograms["confidence_scores"].append(confidence)

        # Update per-stage metrics
        self.by_stage[stage]["count"] += 1
        self.by_stage[stage]["latencies"].append(latency_ms)
        self.by_stage[stage]["costs"].append(cost_usd)
        self.by_stage[stage]["confidences"].append(confidence)

        # Keep memory bounded (last 10k turns)
        if len(self.turns) > 10000:
            self.turns = self.turns[-10000:]

    def get_cascade_distribution(self) -> Dict[str, float]:
        """Get distribution of cascade stages (percentage).

        Returns:
            Dict mapping stage to percentage (0.0-1.0)

        Example:
            {
                "lexical": 0.45,
                "embedding": 0.40,
                "llm_semantic": 0.15
            }
        """
        total = self.counters["turns_total"]
        if total == 0:
            return {}

        return {
            "lexical": self.counters["cascade_stage_lexical"] / total,
            "embedding": self.counters["cascade_stage_embedding"] / total,
            "llm_semantic": self.counters["cascade_stage_llm_semantic"] / total,
            "none": self.counters["cascade_stage_none"] / total,
        }

    def get_average_cost(self) -> float:
        """Get average cost per turn.

        Returns:
            Average cost in USD
        """
        costs = self.histograms["cost_per_turn"]
        return statistics.mean(costs) if costs else 0.0

    def get_total_cost(self) -> float:
        """Get total cost across all turns.

        Returns:
            Total cost in USD
        """
        return sum(self.histograms["cost_per_turn"])

    def get_p50_latency(self) -> float:
        """Get P50 (median) latency.

        Returns:
            P50 latency in milliseconds
        """
        latencies = self.histograms["latency_ms"]
        return statistics.median(latencies) if latencies else 0.0

    def get_p95_latency(self) -> float:
        """Get P95 latency (95th percentile).

        Returns:
            P95 latency in milliseconds
        """
        latencies = sorted(self.histograms["latency_ms"])
        if not latencies:
            return 0.0

        idx = int(len(latencies) * 0.95)
        return latencies[idx] if idx < len(latencies) else latencies[-1]

    def get_p99_latency(self) -> float:
        """Get P99 latency (99th percentile).

        Returns:
            P99 latency in milliseconds
        """
        latencies = sorted(self.histograms["latency_ms"])
        if not latencies:
            return 0.0

        idx = int(len(latencies) * 0.99)
        return latencies[idx] if idx < len(latencies) else latencies[-1]

    def get_average_confidence(self) -> float:
        """Get average confidence score.

        Returns:
            Average confidence (0.0-1.0)
        """
        confidences = self.histograms["confidence_scores"]
        return statistics.mean(confidences) if confidences else 0.0

    def get_stage_stats(self, stage: str) -> Dict[str, float]:
        """Get statistics for a specific cascade stage.

        Args:
            stage: Stage name ("lexical", "embedding", "llm_semantic")

        Returns:
            Dict with count, avg_latency, avg_cost, avg_confidence
        """
        if stage not in self.by_stage:
            return {
                "count": 0,
                "avg_latency_ms": 0.0,
                "avg_cost_usd": 0.0,
                "avg_confidence": 0.0
            }

        data = self.by_stage[stage]
        return {
            "count": data["count"],
            "avg_latency_ms": statistics.mean(data["latencies"]) if data["latencies"] else 0.0,
            "avg_cost_usd": statistics.mean(data["costs"]) if data["costs"] else 0.0,
            "avg_confidence": statistics.mean(data["confidences"]) if data["confidences"] else 0.0
        }

    def get_summary(self) -> str:
        """Get human-readable metrics summary.

        Returns:
            Formatted string with key metrics
        """
        if self.counters["turns_total"] == 0:
            return "No metrics collected yet"

        dist = self.get_cascade_distribution()

        lines = [
            "LGDL Metrics Summary",
            "=" * 60,
            f"\nTotal turns: {self.counters['turns_total']}",
            "",
            "Cascade Distribution:",
            f"  Lexical:      {dist.get('lexical', 0.0) * 100:5.1f}%  (exact matches)",
            f"  Embedding:    {dist.get('embedding', 0.0) * 100:5.1f}%  (semantic similarity)",
            f"  LLM Semantic: {dist.get('llm_semantic', 0.0) * 100:5.1f}%  (context-aware)",
            f"  No match:     {dist.get('none', 0.0) * 100:5.1f}%",
            "",
            "Performance:",
            f"  P50 latency:  {self.get_p50_latency():6.1f} ms",
            f"  P95 latency:  {self.get_p95_latency():6.1f} ms",
            f"  P99 latency:  {self.get_p99_latency():6.1f} ms",
            "",
            "Cost:",
            f"  Average/turn: ${self.get_average_cost():.6f}",
            f"  Total cost:   ${self.get_total_cost():.4f}",
            "",
            "Quality:",
            f"  Avg confidence: {self.get_average_confidence():.3f}",
        ]

        # Per-stage breakdown
        lines.append("\nPer-Stage Breakdown:")
        for stage in ["lexical", "embedding", "llm_semantic"]:
            stats = self.get_stage_stats(stage)
            if stats["count"] > 0:
                lines.append(f"  {stage.upper()}:")
                lines.append(f"    Count:      {stats['count']}")
                lines.append(f"    Latency:    {stats['avg_latency_ms']:.1f} ms")
                lines.append(f"    Cost:       ${stats['avg_cost_usd']:.6f}")
                lines.append(f"    Confidence: {stats['avg_confidence']:.3f}")

        return "\n".join(lines)

    def check_targets(self) -> Dict[str, bool]:
        """Check if metrics meet Phase 1 target goals.

        Target goals:
        - Cost per turn: <$0.01
        - P95 latency: <500ms
        - Average confidence: >0.75

        Returns:
            Dict mapping target to pass/fail boolean
        """
        return {
            "cost_target_met": self.get_average_cost() < 0.01,
            "latency_target_met": self.get_p95_latency() < 500.0,
            "confidence_target_met": self.get_average_confidence() > 0.75,
        }

    def reset(self):
        """Reset all metrics (for testing)."""
        self.turns = []
        self.counters = {k: 0 for k in self.counters}
        self.histograms = {k: [] for k in self.histograms}
        self.by_stage = defaultdict(lambda: {
            "count": 0,
            "latencies": [],
            "costs": [],
            "confidences": []
        })


# Global metrics instance (singleton)
_global_metrics: Optional[LGDLMetrics] = None


def get_global_metrics() -> LGDLMetrics:
    """Get global metrics instance (singleton).

    Returns:
        Global LGDLMetrics instance
    """
    global _global_metrics
    if _global_metrics is None:
        _global_metrics = LGDLMetrics()
    return _global_metrics


def record_turn(stage: str, confidence: float, latency_ms: float, cost_usd: float = 0.0):
    """Convenience function to record turn in global metrics.

    Args:
        stage: Cascade stage
        confidence: Match confidence
        latency_ms: Processing latency
        cost_usd: Estimated cost
    """
    get_global_metrics().record_turn(stage, confidence, latency_ms, cost_usd)
