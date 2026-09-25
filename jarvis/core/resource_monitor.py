import os
import psutil
from typing import Dict, Any


class ResourceMonitor:
    """
    Resource Limits & Health Monitoring enforcing Rule 13:
    Idle: 2-3 GB RAM
    Normal: 4-6 GB RAM
    Hard max: 8 GB RAM
    """

    HARD_MAX_MB = 8192
    NORMAL_MAX_MB = 6144
    IDLE_TARGET_MB = 3072

    @classmethod
    def get_current_process_memory_mb(cls) -> float:
        process = psutil.Process(os.getpid())
        mem_bytes = process.memory_info().rss
        return float(mem_bytes / (1024 * 1024))

    @classmethod
    def get_system_memory_info(cls) -> Dict[str, Any]:
        mem = psutil.virtual_memory()
        return {
            "total_mb": mem.total / (1024 * 1024),
            "available_mb": mem.available / (1024 * 1024),
            "used_mb": mem.used / (1024 * 1024),
            "percent_used": mem.percent,
            "process_rss_mb": cls.get_current_process_memory_mb(),
        }

    @classmethod
    def check_memory_health(cls) -> Dict[str, Any]:
        process_mem = cls.get_current_process_memory_mb()
        if process_mem > cls.HARD_MAX_MB:
            return {
                "healthy": False,
                "status": "EXCEEDED_HARD_MAX",
                "message": f"Process memory {process_mem:.1f} MB exceeds hard maximum budget of {cls.HARD_MAX_MB} MB (Rule 13).",
                "process_mem_mb": process_mem,
            }
        if process_mem > cls.NORMAL_MAX_MB:
            return {
                "healthy": True,
                "status": "WARNING_HIGH_MEMORY",
                "message": f"Process memory {process_mem:.1f} MB is above normal limit of {cls.NORMAL_MAX_MB} MB.",
                "process_mem_mb": process_mem,
            }
        return {
            "healthy": True,
            "status": "HEALTHY",
            "message": f"Process memory {process_mem:.1f} MB within normal operating limits.",
            "process_mem_mb": process_mem,
        }
