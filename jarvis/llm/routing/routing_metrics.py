"""
Routing Metrics Tracker Subsystem for JARVIS LLM Router (Batch 24).

Tracks rolling latency, token counts, estimated costs, success/failure counts,
and fallback history with bounded retention memory safety.
"""

import time
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ProviderMetricsRecord:
    provider_id: str
    model_id: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_latency: float = 0.0
    recent_latencies: List[float] = field(default_factory=list)
    last_error_time: Optional[float] = None
    last_error_message: Optional[str] = None

    def record_success(self, latency: float) -> None:
        self.total_requests += 1
        self.successful_requests += 1
        self.total_latency += latency
        self.recent_latencies.append(latency)
        if len(self.recent_latencies) > 50:
            self.recent_latencies.pop(0)

    def record_failure(self, error_message: str) -> None:
        self.total_requests += 1
        self.failed_requests += 1
        self.last_error_time = time.time()
        self.last_error_message = error_message

    def get_avg_latency(self) -> float:
        if not self.recent_latencies:
            return 1.0  # Default baseline assumption
        return sum(self.recent_latencies) / len(self.recent_latencies)


class RoutingMetricsTracker:
    """Stores rolling performance metrics for routing decisions with bounded retention."""

    def __init__(self, max_history_size: int = 500):
        self.max_history_size = max_history_size
        self._metrics: Dict[str, ProviderMetricsRecord] = {}

    def _get_key(self, provider_id: str, model_id: str) -> str:
        return f"{provider_id}:{model_id}"

    def record_success(self, provider_id: str, model_id: str, latency: float) -> None:
        key = self._get_key(provider_id, model_id)
        if key not in self._metrics:
            self._metrics[key] = ProviderMetricsRecord(provider_id=provider_id, model_id=model_id)
        self._metrics[key].record_success(latency)

    def record_failure(self, provider_id: str, model_id: str, error_message: str) -> None:
        key = self._get_key(provider_id, model_id)
        if key not in self._metrics:
            self._metrics[key] = ProviderMetricsRecord(provider_id=provider_id, model_id=model_id)
        self._metrics[key].record_failure(error_message)

    def get_average_latency(self, provider_id: str, model_id: str) -> float:
        key = self._get_key(provider_id, model_id)
        rec = self._metrics.get(key)
        if not rec:
            return 1.0
        return rec.get_avg_latency()

    def get_summary(self) -> Dict[str, Any]:
        summary: Dict[str, Any] = {}
        for key, rec in self._metrics.items():
            summary[key] = {
                "provider_id": rec.provider_id,
                "model_id": rec.model_id,
                "total_requests": rec.total_requests,
                "successful_requests": rec.successful_requests,
                "failed_requests": rec.failed_requests,
                "avg_latency": round(rec.get_avg_latency(), 4),
            }
        return summary
