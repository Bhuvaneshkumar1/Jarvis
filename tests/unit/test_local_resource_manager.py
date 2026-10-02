"""
Unit Tests for LocalResourceManager (Batch 23).
Tests memory estimation, available system RAM checks, and max memory limits.
"""

from jarvis.llm.local_runtime.resource_manager import LocalResourceManager


def test_system_memory_status():
    mem_status = LocalResourceManager.get_system_memory_status()
    assert "total_mb" in mem_status
    assert "available_mb" in mem_status
    assert "used_mb" in mem_status
    assert mem_status["total_mb"] > 0
    assert mem_status["available_mb"] > 0


def test_estimate_model_memory_mb():
    mgr = LocalResourceManager(max_memory_mb=4096.0)
    # 2 GB model file (2048 MB bytes)
    file_bytes = 2048 * 1024 * 1024
    est_mb = mgr.estimate_model_memory_mb(file_bytes, context_window=2048)
    # Weights ~2355 MB + KV Cache ~256 MB + Overhead 200 MB = ~2811 MB
    assert 2700.0 <= est_mb <= 2900.0


def test_can_load_model_exceeds_max_limit():
    # Set ceiling at 1000 MB
    mgr = LocalResourceManager(max_memory_mb=1000.0)
    # 2 GB model file
    file_bytes = 2048 * 1024 * 1024
    can_load, reason = mgr.can_load_model(file_bytes, context_window=2048)

    assert can_load is False
    assert "exceeds configured max memory limit" in reason


def test_can_load_model_within_limit():
    mgr = LocalResourceManager(max_memory_mb=8192.0)
    # Small 100 MB dummy model
    file_bytes = 100 * 1024 * 1024
    can_load, reason = mgr.can_load_model(file_bytes, context_window=2048)

    assert can_load is True
    assert "Resource check passed" in reason
