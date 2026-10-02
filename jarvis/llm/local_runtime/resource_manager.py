"""
Local Resource Manager for JARVIS (Batch 23).

Enforces system RAM and configured local LLM memory limits, estimates GGUF model memory consumption,
and prevents resource exhaustion during local LLM model loading and inference.
"""

import os
from typing import Dict, Tuple
import psutil

import logging

logger = logging.getLogger(__name__)


class LocalResourceManager:
    """Monitors system memory and enforces resource safety limits for local inference."""

    def __init__(self, max_memory_mb: float = 4096.0, max_concurrency: int = 1):
        self.max_memory_mb = max_memory_mb
        self.max_concurrency = max_concurrency

    @staticmethod
    def get_system_memory_status() -> Dict[str, float]:
        """Returns total, available, and used system memory in MB."""
        mem = psutil.virtual_memory()
        return {
            "total_mb": round(mem.total / (1024 * 1024), 2),
            "available_mb": round(mem.available / (1024 * 1024), 2),
            "used_mb": round(mem.used / (1024 * 1024), 2),
            "percent_used": mem.percent,
        }

    @staticmethod
    def get_process_memory_mb() -> float:
        """Returns current process RSS memory in MB."""
        process = psutil.Process(os.getpid())
        return float(round(process.memory_info().rss / (1024 * 1024), 2))

    def estimate_model_memory_mb(self, file_size_bytes: int, context_window: int = 2048) -> float:
        """
        Estimates total RAM required for loading model weights + context window KV cache + runtime overhead.

        Formula:
        Base model memory = File Size MB * 1.15 (quantized overhead/tensors)
        KV Cache memory = (context_window / 2048) * 256 MB (approx for 7B fp16/q4 KV cache)
        Runtime overhead = 200 MB
        """
        file_size_mb = file_size_bytes / (1024 * 1024)
        weights_mb = file_size_mb * 1.15
        kv_cache_mb = (context_window / 2048.0) * 256.0
        overhead_mb = 200.0

        estimated_mb = weights_mb + kv_cache_mb + overhead_mb
        return float(round(estimated_mb, 2))

    def can_load_model(self, file_size_bytes: int, context_window: int = 2048) -> Tuple[bool, str]:
        """
        Validates if model can be safely loaded without exceeding system memory or configured limits.

        Returns (allowed: bool, reason: str).
        """
        estimated_mb = self.estimate_model_memory_mb(file_size_bytes, context_window)
        sys_mem = self.get_system_memory_status()
        available_mb = sys_mem["available_mb"]

        # Check configured max memory limit
        if estimated_mb > self.max_memory_mb:
            return False, (f"Estimated model memory ({estimated_mb} MB) exceeds configured max memory limit LOCAL_LLM_MAX_MEMORY_MB ({self.max_memory_mb} MB).")

        # Check system available memory (leave a 512 MB safety buffer)
        safety_buffer_mb = 512.0
        if estimated_mb > (available_mb - safety_buffer_mb):
            return False, (
                f"Insufficient available system memory ({available_mb} MB available). "
                f"Model requires estimated {estimated_mb} MB + {safety_buffer_mb} MB safety buffer."
            )

        return (
            True,
            f"Resource check passed: Model requires est. {estimated_mb} MB (Available: {available_mb} MB).",
        )
