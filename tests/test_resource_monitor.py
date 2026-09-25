from jarvis.core.resource_monitor import ResourceMonitor

def test_resource_monitor_health():
    info = ResourceMonitor.get_system_memory_info()
    assert "total_mb" in info
    assert "process_rss_mb" in info
    assert info["process_rss_mb"] > 0

    health = ResourceMonitor.check_memory_health()
    assert "healthy" in health
    assert "status" in health
